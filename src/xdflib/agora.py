"""
Agora RTC 客户端 — Token 生成和频道管理。

Token 生成无需网络请求，使用 HMAC-SHA256 本地完成。
频道查询使用 Agora REST API。

音频配置常量与 Java RtcEngineManager.java 匹配。
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import requests

from .config import (
    AGORA_AUDIO_PROFILE,
    AGORA_AUDIO_SCENARIO,
    AGORA_CHANNEL_PROFILE,
    AGORA_CLIENT_ROLE,
)

logger = logging.getLogger("xdflib.agora")


class AgoraClient:
    """
    Agora RTC 客户端。

    使用示例:
        agora = AgoraClient(app_id="...", app_certificate="...")
        token = agora.generate_token(channel="room_001", uid=12345)
        users = agora.list_channel_users(channel="room_001")
    """

    REST_BASE = "https://api.agora.io/dev/v1"

    def __init__(
        self,
        app_id: str = "",
        app_certificate: str = "",
    ):
        self.app_id = app_id
        self.app_certificate = app_certificate

    # ── Token 生成（本地） ──

    def generate_token(
        self,
        channel: str,
        uid: int = 0,
        *,
        expire_seconds: int = 3600,
        role: int = 1,  # 1 = 主播（发布者）
    ) -> str:
        """
        生成 Agora RTC Token（简化实现）。

        **注意**: 当前使用简化格式，不包含 Agora 官方的完整二进制结构
        （CRC、salt、privilege 等字段）。在部分 Agora SDK 版本中可能被拒绝。

        生产环境建议使用官方 `agora-token` 包或实现完整二进制协议。

        参数:
            channel:        频道名称。
            uid:            用户 ID（0 = 自动分配）。
            expire_seconds: Token 有效期。
            role:           1 = 主播（发布者），2 = 观众。

        返回:
            Agora RTC Token 字符串。
        """
        if not self.app_certificate:
            raise ValueError("生成 Token 需要 app_certificate")

        ts = int(time.time()) + expire_seconds
        # Agora Token 格式: "appId:ts:role:uid"
        # 但实际上使用的是更简单的版本
        sign_str = f"{self.app_id}{self.app_certificate}{channel}{uid}{ts}{role}"
        signature = hmac.new(
            self.app_certificate.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 简化的 Token 格式（v1 风格，向后兼容）
        token = f"006{self.app_id}{signature}{self.app_id}{channel}{uid}{ts}"
        return token

    # ── 频道查询（REST API） ──

    def list_channel_users(self, channel: str) -> list[dict[str, Any]]:
        """
        查询频道中活跃用户列表。

        使用 Agora REST API: GET /channel/user/{appId}/{channelName}
        需要 app_certificate 进行 HTTP Basic Auth。

        返回:
            用户对象列表，每个包含 {uid, join_time, ...} 字段。
        """
        if not self.app_certificate:
            logger.warning("频道查询需要 app_certificate")
            return []

        url = f"{self.REST_BASE}/channel/user/{self.app_id}/{channel}"
        try:
            resp = requests.get(
                url,
                auth=(self.app_id, self.app_certificate),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data.get("data", {}).get("users", [])
            else:
                logger.warning("频道查询失败: %s", data)
                return []
        except requests.exceptions.RequestException as e:
            logger.error("频道查询失败: %s", e)
            return []

    # ── 配置 ──

    def build_default_config(self) -> dict[str, Any]:
        """
        返回与 Java RtcEngineManager.setupConfig() 匹配的 Agora 引擎配置。

        - 音频 Profile:   0（DEFAULT/语音），场景 3（GAME_STREAMING 低延迟）
        - 频道 Profile:   1（LIVE_BROADCASTING）
        - 客户端角色:     1（BROADCASTER）
        - 自动订阅音频/视频: 是
        - 发布本地音频/视频: 是
        """
        return {
            "audio_profile": AGORA_AUDIO_PROFILE,
            "audio_scenario": AGORA_AUDIO_SCENARIO,
            "channel_profile": AGORA_CHANNEL_PROFILE,
            "client_role": AGORA_CLIENT_ROLE,
            "auto_subscribe_audio": True,
            "auto_subscribe_video": True,
            "publish_local_audio": True,
            "publish_local_video": True,
        }
