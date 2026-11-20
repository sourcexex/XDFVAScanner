"""
TLSSigAPIv2 — 腾讯云 IM UserSig 签名生成器。

复现腾讯官方的 TLSSigAPIv2 签名算法。
参考: https://github.com/TencentCloud/tc-signature
"""

import base64
import hashlib
import hmac
import json
import time
import zlib


def _base64_url_encode(data: bytes) -> str:
    """Base64 URL 安全编码（无填充）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def gen_user_sig(
    sdk_app_id: int,
    secret_key: str,
    user_id: str,
    expire: int = 180 * 86400,  # 默认 180 天
) -> str:
    """
    为普通用户生成 TLSSigAPIv2 UserSig。

    参数:
        sdk_app_id: 腾讯云 IM 应用的 SDKAppID。
        secret_key: 来自腾讯云 IM 控制台的应用密钥。
        user_id:    用户 ID（identifier）。
        expire:     UserSig 有效期，以秒为单位（默认 180 天）。

    返回:
        Base64 编码的 UserSig 字符串，格式为 "{compressed}.{signature}"。
    """
    curr_time = int(time.time())

    # 构造签名文档
    sig_doc: dict[str, object] = {
        "TLS.ver": "2.0",
        "TLS.identifier": str(user_id),
        "TLS.sdkappid": sdk_app_id,
        "TLS.expire": expire,
        "TLS.time": curr_time,
    }

    # 如果 expire 超过 uint32 最大值，使用 expire_64
    if expire > 0xFFFFFFFF:
        sig_doc["TLS.expire"] = 0xFFFFFFFF
        sig_doc["TLS.expire_64"] = expire

    # JSON 序列化 → zlib 压缩
    json_str = json.dumps(sig_doc, separators=(",", ":"))
    compressed = zlib.compress(json_str.encode("utf-8"))

    # Base64URL 编码压缩结果
    base64_compressed = _base64_url_encode(compressed)

    # HMAC-SHA256 签名
    signature_bytes = hmac.new(
        secret_key.encode("utf-8"),
        base64_compressed.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    signature = _base64_url_encode(signature_bytes)

    return base64_compressed + "." + signature


def gen_admin_user_sig(
    sdk_app_id: int,
    secret_key: str,
    admin_id: str,
    expire: int = 180 * 86400,
) -> str:
    """
    为管理员生成 UserSig（与普通 UserSig 相同，但用于 REST API 认证）。

    管理员账号用于调用腾讯云 IM REST API。
    """
    return gen_user_sig(sdk_app_id, secret_key, admin_id, expire)
