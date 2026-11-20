"""
XDF 认证加密工具函数。

复现自 APK 的 AESCBCUtil.java、ApiMac.java 和 EncryptHeaderInterceptor.java。
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


# ================================================================
#  AES-CBC 加密（复现 APK AESCBCUtil.encodeAES()）
#  AES/CBC/PKCS5Padding，IV = 密钥的后 16 字节
# ================================================================


def aes_encrypt(plaintext: str, key_32: str) -> str:
    """
    使用 AES-256-CBC 加密，以 PKCS7 填充，输出 Base64。

    参数:
        plaintext: 要加密的明文字符串。
        key_32:    32 字符的 ASCII 密钥（密钥 = 全部 32 字节，IV = 后 16 字节）。

    返回:
        Base64 编码的密文。
    """
    key_bytes = key_32.encode("utf-8")
    iv_bytes = key_bytes[16:]  # 后 16 字节作为 IV

    data = plaintext.encode("utf-8")

    # PKCS7 填充
    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded = data + bytes([padding_len] * padding_len)

    cipher = Cipher(
        algorithms.AES(key_bytes),
        modes.CBC(iv_bytes),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(encrypted).decode("ascii")


# ================================================================
#  HMAC-SHA1 签名（复现 APK ApiMac.sign()）
#  sign = Base64(HMAC-SHA1(appSecret, requestBody))
# ================================================================


def hmac_sha1_sign(data: str, secret: str) -> str:
    """HMAC-SHA1 签名，以 Base64 输出。"""
    mac = hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    )
    return base64.b64encode(mac.digest()).decode("ascii")


# ================================================================
#  sdkSign 计算（复现 APK EncryptHeaderInterceptor）
#  sdkSign = MD5(timestamp + guid + deviceId + u2AppKey)
# ================================================================


def compute_sdk_sign(timestamp: str, guid: str, device_id: str, u2_app_key: str) -> str:
    """计算 sdkSign 请求头值。"""
    raw = timestamp + guid + device_id + u2_app_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ================================================================
#  请求头编码（复现 APK EncryptHeaderInterceptor.encodeHeadInfo()）
#  控制字符和 >= 127 的字节转义为 \\uXXXX
# ================================================================


def _encode_header(value: str) -> str:
    """对请求头值进行编码，将特殊字符转义为 Unicode 转义序列。"""
    result: list[str] = []
    for c in value:
        code = ord(c)
        if code <= 31 or code >= 127:
            result.append(f"\\u{code:04x}")
        else:
            result.append(c)
    return "".join(result)


# ================================================================
#  设备信息（模拟 Android 平板）
# ================================================================


def generate_device_info() -> dict[str, str]:
    """为 XDF 登录 API 生成伪造的设备指纹。"""
    device_raw = f"python-xdflib-{uuid.getnode()}"
    device_id = hashlib.md5(device_raw.encode()).hexdigest()
    return {
        "deviceId": device_id,
        "devicePlatform": "APP",
        "deviceType": "ANDROID_MOBILE",
        "brand": "XDFLib",
        "deviceModel": "Python Simulator",
        "osVersion": "11",
        "isRoot": "0",
        "lon": "0",
        "lat": "0",
        "appVersion": "1.2.0",
        "appName": "XDFLib",
    }


# ================================================================
#  请求签名工具函数
# ================================================================


def build_signature_headers(
    path_and_query: str,
    body: dict[str, Any] | None,
    env_config,  # XDFEnvConfig
    device_info: dict[str, str],
) -> dict[str, str]:
    """
    为 XDF API 请求构造完整的签名 + 设备指纹请求头集合。

    参数:
        path_and_query: URL 路径，可选带查询字符串（例如 "/sdkapi/login/account"）。
        body:           请求体字典（POST 时签名负载；GET 时为 None）。
        env_config:     环境配置（ENV_PROD 或 ENV_TEST）。
        device_info:    设备指纹（来自 generate_device_info()）。

    返回:
        用于 requests 库的请求头字典。
    """
    timestamp = str(int(time.time() * 1000))
    guid = str(uuid.uuid4())
    device_id = device_info["deviceId"]

    # POST 时对 JSON 负载签名，GET 时对路径+查询字符串签名
    if body is not None:
        sign_input = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    else:
        sign_input = path_and_query

    sign = hmac_sha1_sign(sign_input, env_config.app_secret)
    sdk_sign = compute_sdk_sign(timestamp, guid, device_id, env_config.u2_app_key)

    return {
        "Content-Type": "application/json",
        "User-Agent": "Dalvik/2.1.0",
        "appId": env_config.app_id,
        "sign": _encode_header(sign),
        "u2AppId": env_config.u2_app_id,
        "deviceId": _encode_header(device_id),
        "devicePlatform": device_info["devicePlatform"],
        "deviceType": device_info["deviceType"],
        "originIp": "127.0.0.1",
        "originReferer": "127.0.0.1",
        "originUserAgent": "Mozilla/5.0",
        "appVersion": device_info["appVersion"],
        "timestamp": timestamp,
        "guid": guid,
        "sdkSign": sdk_sign,
        "brand": device_info["brand"],
        "deviceModel": device_info["deviceModel"],
        "osVersion": device_info["osVersion"],
        "isRoot": device_info["isRoot"],
        "lon": device_info["lon"],
        "lat": device_info["lat"],
        "appName": device_info["appName"],
    }
