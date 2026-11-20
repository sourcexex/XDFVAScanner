/**
 * XDFLib IM Bridge — Node.js persistent process wrapping @tencentcloud/chat SDK.
 * Protocol: stdin JSON commands → stdout JSON events.
 *
 * Commands:
 *   {"cmd":"login", "sdkAppId":N, "userId":"...", "userSig":"..."}
 *   {"cmd":"send", "id":"req1", "to":"...", "text":"Hello"}
 *   {"cmd":"send_custom", "id":"req2", "to":"...", "data":"{...}", "desc":"...", "ext":"..."}
 *   {"cmd":"send_image", "id":"req3", "to":"...", "path":"/abs/path/to/file"}
 *   {"cmd":"send_video", "id":"req4", "to":"...", "path":"/abs/path/to/file"}
 *   {"cmd":"send_file",  "id":"req5", "to":"...", "path":"/abs/path/to/file"}
 *   {"cmd":"quit"}
 *
 * Events:
 *   {"event":"ready"}
 *   {"event":"sent", "id":"req1", "success":true, "msgId":"...", "msgTime":N}
 *   {"event":"message","data":{"id":"...", "type":"...", "from":"...", "to":"...", "time":N, "payload":{...}}}
 *   {"event":"error", "error":"..."}
 */

const TencentCloudChat = require('@tencentcloud/chat');
const fs = require('fs');
const path = require('path');

// 将所有 SDK 日志重定向到 stderr，保持 stdout 的 JSON 协议干净
const _origLog = console.log;
console.log = (...args) => process.stderr.write('Chat  ' + args.join(' ') + '\n');
console.warn = (...args) => process.stderr.write('Chat  ' + args.join(' ') + '\n');
console.error = (...args) => process.stderr.write('Chat  ' + args.join(' ') + '\n');
console.info = (...args) => process.stderr.write('Chat  ' + args.join(' ') + '\n');
console.debug = (...args) => process.stderr.write('Chat  ' + args.join(' ') + '\n');

let chat = null;
let loggedIn = false;

function emit(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }
function logErr(m) { process.stderr.write(`[bridge] ${m}\n`); }

// ── Message handler ──
function onMessage(event) {
    for (const msg of (event.data || [])) {
        emit({ event: 'message', data: { id: msg.ID, type: msg.type, from: msg.from, to: msg.to, time: msg.time, payload: msg.payload || {} } });
    }
}

// ── Media sender ──
async function sendMedia(cmdId, createFn, to, filePath) {
    if (!filePath || !fs.existsSync(filePath)) {
        emit({ event: 'sent', id: cmdId, success: false, error: `File not found: ${filePath}` });
        return;
    }
    const msg = createFn({
        to, conversationType: TencentCloudChat.TYPES.CONV_C2C,
        payload: { file: { tempFilePath: filePath, name: path.basename(filePath) } },
        onProgress: () => {},
    });
    const result = await chat.sendMessage(msg);
    emit({ event: 'sent', id: cmdId, success: true, msgId: result.data.message.ID, msgTime: result.data.message.time });
}

// ── Command handler ──
async function handle(cmd) {
    const { cmd: c, id } = cmd;
    try {
        if (c === 'login') {
            chat = TencentCloudChat.create({ SDKAppID: cmd.sdkAppId });
            chat.setLogLevel(4);
            chat.on(TencentCloudChat.EVENT.SDK_READY, () => { loggedIn = true; emit({ event: 'sent', id: 'login', success: true }); });
            chat.on(TencentCloudChat.EVENT.SDK_NOT_READY, () => { loggedIn = false; emit({ event: 'sent', id: 'login', success: false, error: 'SDK_NOT_READY — UserSig 可能无效或已过期' }); });
            chat.on(TencentCloudChat.EVENT.KICKED_OUT, () => { loggedIn = false; emit({ event: 'sent', id: 'login', success: false, error: 'KICKED_OUT — 账号在其他设备登录' }); });
            chat.on(TencentCloudChat.EVENT.MESSAGE_RECEIVED, onMessage);
            chat.on(TencentCloudChat.EVENT.ERROR, (e) => {
                if ((e.data && e.data.errorCode) !== 2801) logErr(`SDK err: ${e.data && e.data.errorCode}`);
            });
            await chat.login({ userID: cmd.userId, userSig: cmd.userSig });
        } else if (c === 'send') {
            if (!loggedIn) { emit({ event: 'sent', id, success: false, error: 'Not logged in' }); return; }
            let m;
            if (cmd.text !== undefined) m = chat.createTextMessage({ to: cmd.to, conversationType: TencentCloudChat.TYPES.CONV_C2C, payload: { text: cmd.text } });
            else if (cmd.customData !== undefined) m = chat.createCustomMessage({ to: cmd.to, conversationType: TencentCloudChat.TYPES.CONV_C2C, payload: { data: cmd.customData, description: '', extension: '' } });
            else m = chat.createCustomMessage({ to: cmd.to, conversationType: TencentCloudChat.TYPES.CONV_C2C, payload: { data: JSON.stringify(cmd.body || {}), description: '', extension: '' } });
            if (cmd.push) {
                if (typeof m.setOfflinePushInfo === 'function') {
                    m.setOfflinePushInfo(cmd.push);
                }
            }
            const r = await chat.sendMessage(m);
            emit({ event: 'sent', id, success: true, msgId: r.data.message.ID, msgTime: r.data.message.time });
        } else if (c === 'send_custom') {
            if (!loggedIn) { emit({ event: 'sent', id, success: false, error: 'Not logged in' }); return; }
            const m = chat.createCustomMessage({ to: cmd.to, conversationType: TencentCloudChat.TYPES.CONV_C2C, payload: { data: cmd.data || '', description: cmd.desc || '', extension: cmd.ext || '' } });
            const r = await chat.sendMessage(m);
            emit({ event: 'sent', id, success: true, msgId: r.data.message.ID, msgTime: r.data.message.time });
        } else if (c === 'send_image') await sendMedia(id, (opts) => chat.createImageMessage(opts), cmd.to, cmd.path);
        else if (c === 'send_video') await sendMedia(id, (opts) => chat.createVideoMessage(opts), cmd.to, cmd.path);
        else if (c === 'send_file')  await sendMedia(id, (opts) => chat.createFileMessage(opts), cmd.to, cmd.path);
        else if (c === 'quit') {
            try { if (chat && loggedIn) await chat.logout(); } catch (e) {}
            process.exit(0);
        } else emit({ event: 'error', id, error: `Unknown command: ${c}` });
    } catch (err) {
        logErr(`${c}: ${err.message}`);
        emit({ event: 'sent', id, success: false, error: err.message });
    }
}

// ── stdin reader ──
let buf = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', async (chunk) => {
    buf += chunk;
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const l of lines) {
        const s = l.trim();
        if (!s) continue;
        try { await handle(JSON.parse(s)); } catch (e) { logErr(`Parse: ${e.message}`); emit({ event: 'error', error: e.message }); }
    }
});
process.stdin.on('end', () => process.exit(0));
process.on('SIGINT', () => { if (chat && loggedIn) chat.logout().catch(()=>{}).finally(()=>process.exit(0)); else process.exit(0); });
process.on('SIGTERM', () => { if (chat && loggedIn) chat.logout().catch(()=>{}).finally(()=>process.exit(0)); else process.exit(0); });

// Idle timeout (1 hour)
let timer = setTimeout(() => { logErr('Idle timeout'); process.exit(0); }, 3600000);
const orig = handle; handle = (c) => { clearTimeout(timer); timer = setTimeout(() => { logErr('Idle timeout'); process.exit(0); }, 3600000); return orig(c); };

logErr('Bridge started, waiting for commands...');
