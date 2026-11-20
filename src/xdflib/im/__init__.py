"""IM 子包 — 消息构造、传输、解析。"""

from .client import IMClient
from .rest import IMRestClient
from .bridge import IMBridgeClient
from .base import IMBaseClient, MessageType
from .messages import (
    build_text,
    build_image,
    build_video,
    build_file,
    build_system_correct,
    build_course_card,
    build_calling,
    build_offline_push,
    parse_message,
    parse_message_from_bridge,
)

__all__ = [
    "IMClient",
    "IMRestClient",
    "IMBridgeClient",
    "IMBaseClient",
    "MessageType",
    "build_text",
    "build_image",
    "build_video",
    "build_file",
    "build_system_correct",
    "build_course_card",
    "build_calling",
    "build_offline_push",
    "parse_message",
    "parse_message_from_bridge",
]
