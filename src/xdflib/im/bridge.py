"""
IM Bridge 客户端 — Node.js 子进程管理。

生成一个运行 @tencentcloud/chat SDK 的 Node.js 子进程，
通过 stdin/stdout JSON 行协议进行通信。
支持实时消息接收和本地文件发送（图片、视频、文件）。
"""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue, Empty

from ..config import IM_SDK_APP_ID
from ..models import SendResult
from .base import IMBaseClient
from .messages import parse_message_from_bridge

logger = logging.getLogger("xdflib.im.bridge")

def _resolve_bridge_dir() -> Path:
    """
    定位 Node 桥接脚本所在目录。

    查找顺序:
        1. 环境变量 ``XDFLIB_BRIDGE_DIR``
        2. 源码布局: ``<repo>/bridge``（本文件向上 4 层）
        3. 包内布局: ``<site-packages>/xdflib/bridge``
        4. 当前工作目录下的 ``bridge/``
    """
    candidates: list[Path] = []

    env_dir = os.environ.get("XDFLIB_BRIDGE_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir))

    here = Path(__file__).resolve()
    candidates.append(here.parents[3] / "bridge")   # 源码布局
    candidates.append(here.parents[1] / "bridge")   # 包内布局
    candidates.append(Path.cwd() / "bridge")        # 从仓库根目录运行时

    for candidate in candidates:
        if (candidate / "bridge.cjs").is_file():
            return candidate
    return candidates[0]


# Bridge 脚本的位置
_BRIDGE_DIR = _resolve_bridge_dir()
_BRIDGE_SCRIPT = _BRIDGE_DIR / "bridge.cjs"


class IMBridgeClient(IMBaseClient):
    """
    用于实时双向 IM 的 Node.js SDK 桥接客户端。

    需要安装 Node.js 和 npm 依赖项（cd bridge && npm install）。

    功能:
    - 通过 @tencentcloud/chat SDK 发送/接收消息
    - 本地文件上传（图片、视频、文件）
    - 通过回调实时接收消息
    """

    def __init__(
        self,
        sdk_app_id: int = IM_SDK_APP_ID,
        *,
        user_id: str = "",
        user_sig: str = "",
    ):
        super().__init__(sdk_app_id)
        self._user_id = user_id
        self.user_sig = user_sig

        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, threading.Event] = {}
        self._responses: dict[str, dict] = {}
        self._reader_thread: threading.Thread | None = None
        self._running = False
        self._connected = False
        self._req_id = 0

    # ── 连接 & 断开 ──

    def connect(self, timeout: float = 30.0) -> bool:
        """启动 Node.js 子进程并登录。"""
        if self._running:
            return self._connected

        if not _BRIDGE_SCRIPT.exists():
            logger.error("Bridge 脚本未找到: %s", _BRIDGE_SCRIPT)
            logger.error(
                "请在本项目 bridge/ 目录执行 npm install，"
                "或用 XDFLIB_BRIDGE_DIR 指定桥接脚本所在目录"
            )
            return False

        logger.info("正在启动 IM Bridge (node %s)...", _BRIDGE_SCRIPT)
        try:
            self._process = subprocess.Popen(
                ["node", str(_BRIDGE_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(_BRIDGE_DIR),
            )
        except FileNotFoundError:
            logger.error("Node.js 未安装或不在 PATH 中")
            return False

        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()

        # 发送登录命令
        login_cmd = {
            "cmd": "login",
            "sdkAppId": self.sdk_app_id,
            "userId": self.user_id,
            "userSig": self.user_sig,
        }
        result = self._send_cmd("login", login_cmd, timeout=timeout)
        if result.get("success"):
            self._connected = True
            logger.info("IM Bridge 已连接 (userId=%s)", self.user_id)
            return True
        else:
            logger.error("IM Bridge 登录失败: %s", result.get("error", "unknown"))
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """优雅关闭 Node.js 子进程。"""
        # 先发送 quit 命令，再关闭读取循环
        if self._process and self._process.stdin:
            try:
                self._send_cmd("quit", {"cmd": "quit"}, timeout=3.0)
            except Exception:
                pass
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            finally:
                self._process = None
        self._connected = False
        logger.info("IM Bridge 已断开")

    # ── 核心发送/接收 ──

    def _send_cmd(self, cmd_id: str, cmd: dict, timeout: float = 30.0) -> dict:
        """向子进程发送 JSON 命令并等待响应。"""
        if not self._process or not self._process.stdin:
            return {"success": False, "error": "进程未运行"}
        if self._process.poll() is not None:
            return {"success": False, "error": f"进程已退出 (code={self._process.returncode})"}

        with self._lock:
            event = threading.Event()
            self._pending[cmd_id] = event

        try:
            line = json.dumps(cmd, ensure_ascii=False)
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError, UnicodeEncodeError) as e:
            with self._lock:
                self._pending.pop(cmd_id, None)
            return {"success": False, "error": str(e)}

        if event.wait(timeout=timeout):
            with self._lock:
                return self._responses.pop(cmd_id, {})
        else:
            with self._lock:
                self._pending.pop(cmd_id, None)
            return {"success": False, "error": "超时"}

    def _read_loop(self) -> None:
        """从 Node.js stdout 读取 JSON 行的事件循环。"""
        if not self._process or not self._process.stdout:
            return

        for line in self._process.stdout:
            if not self._running:
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # 来自 SDK 的良性 stdout 噪音（样式化控制台日志）
                if not line.startswith("Chat  "):
                    logger.debug("Bridge stdout: %s", line[:120])
                continue

            evt_type = event.get("event", "")
            evt_id = event.get("id", "")

            if evt_type == "message":
                # 收到新消息 → 调用回调
                data = event.get("data", {})
                if self._on_message:
                    try:
                        parsed = parse_message_from_bridge(data)
                        self._on_message(parsed)
                    except Exception as e:
                        logger.warning("解析 bridge 消息失败: %s", e)
            elif evt_type in ("ready", "sent", "login_error", "error"):
                # 响应待处理的请求
                with self._lock:
                    self._responses[evt_id or evt_type] = event
                    pending = self._pending.pop(evt_id or evt_type, None)
                if pending:
                    pending.set()

    def _stderr_loop(self) -> None:
        """将 Bridge stderr 读取到 Python logger。"""
        if not self._process or not self._process.stderr:
            return
        for line in self._process.stderr:
            if not self._running:
                break
            line = line.strip()
            if line:
                # 过滤 SDK 内部长轮询超时（code 2801），良性噪音
                if "code: 2801" in line:
                    continue
                logger.info("Bridge | %s", line)

    # ── IMBaseClient 实现 ──

    def send_msg(
        self,
        from_account: str,
        to_account: str,
        msg_body: list[dict],
        *,
        offline_push_info: dict | None = None,
        msg_life_time: int = 604800,
    ) -> SendResult:
        if not self._connected:
            return SendResult(success=False, error_code=-1, error_info="未连接")

        cmd_id = f"send_{self._next_id()}"
        # 提取文本或自定义数据用于 Bridge 发送
        cmd: dict = {
            "cmd": "send",
            "id": cmd_id,
            "to": to_account,
        }
        if msg_body:
            first = msg_body[0]
            if first["MsgType"] == "TIMTextElem":
                cmd["text"] = first["MsgContent"].get("Text", "")
            elif first["MsgType"] == "TIMCustomElem":
                cmd["customData"] = first["MsgContent"].get("Data", "")
            else:
                cmd["body"] = msg_body

        if offline_push_info:
            cmd["push"] = offline_push_info

        result = self._send_cmd(cmd_id, cmd, timeout=30.0)
        if result.get("success"):
            return SendResult(
                success=True,
                msg_key=result.get("msgId", ""),
                msg_time=result.get("msgTime", 0),
            )
        else:
            return SendResult(
                success=False,
                error_code=-1,
                error_info=result.get("error", "发送失败"),
            )

    def batch_send_msg(
        self,
        from_account: str,
        to_accounts: list[str],
        msg_body: list[dict],
        *,
        msg_life_time: int = 604800,
    ) -> SendResult:
        results = []
        for target in to_accounts:
            results.append(self.send_msg(from_account, target, msg_body, msg_life_time=msg_life_time))
        # 如果全部成功则返回成功
        all_ok = all(r.success for r in results)
        return SendResult(success=all_ok, error_info="" if all_ok else "部分发送失败")

    def fetch_history(
        self,
        user_id: str,
        count: int = 20,
        last_msg_key: str | None = None,
    ) -> list:
        # Bridge 模式不支持历史查询（需要 REST API）
        logger.warning("Bridge 模式不支持 fetch_history，请使用 REST API")
        return []

    def fetch_conversations(self) -> list:
        logger.warning("Bridge 模式不支持 fetch_conversations，请使用 REST API")
        return []

    def account_import(self, user_id: str, nick: str = "", face_url: str = "") -> SendResult:
        # Bridge 对已登录用户是免操作
        return SendResult(success=True)

    # ── 便捷媒体发送方法 ──

    def send_image(self, to: str, path: str, *, timeout: float = 120.0) -> SendResult:
        """通过 SDK 上传发送本地图片文件。"""
        return self._send_media("send_image", to, path, timeout=timeout)

    def send_video(self, to: str, path: str, *, timeout: float = 120.0) -> SendResult:
        """通过 SDK 上传发送本地视频文件。"""
        return self._send_media("send_video", to, path, timeout=timeout)

    def send_file(self, to: str, path: str, *, timeout: float = 120.0) -> SendResult:
        """通过 SDK 上传发送本地文件。"""
        return self._send_media("send_file", to, path, timeout=timeout)

    def _send_media(self, cmd_name: str, to: str, path: str, *, timeout: float = 120.0) -> SendResult:
        if not self._connected:
            return SendResult(success=False, error_code=-1, error_info="未连接")
        if not os.path.isfile(path):
            return SendResult(success=False, error_code=-2, error_info=f"文件不存在: {path}")

        cmd_id = f"{cmd_name}_{self._next_id()}"
        cmd = {"cmd": cmd_name, "id": cmd_id, "to": to, "path": os.path.abspath(path)}
        result = self._send_cmd(cmd_id, cmd, timeout=timeout)
        if result.get("success"):
            return SendResult(success=True, msg_key=result.get("msgId", ""))
        else:
            return SendResult(success=False, error_code=-1, error_info=result.get("error", "发送失败"))

    # ── 工具 ──

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    @property
    def user_id(self) -> str:
        """当前登录的 IM 用户 ID。"""
        return self._user_id

    @property
    def is_connected(self) -> bool:
        return self._connected

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
