"""
XDFLib — XDF Pad 通信协议库。

提供 XDF Pad 教育应用的完整协议实现:
- 认证（手机号+密码登录、IM 凭证）
- 即时通讯（发送/接收文本、图片、视频、文件、自定义消息）
- Agora RTC（Token 生成、频道管理）
- 白板信令（通过 IM 通道传输的控制指令）
"""

# ── 环境 & 配置 ──
from .config import (
    ENV_PROD,
    ENV_TEST,
    XDFEnvConfig,
    IM_SDK_APP_ID,
    IM_SYSTEM_USER_ID,
    AGORA_AUDIO_PROFILE,
    AGORA_AUDIO_SCENARIO,
    AGORA_CHANNEL_PROFILE,
    AGORA_CLIENT_ROLE,
)

# ── 异常 ──
from .errors import XDFError, XDFAuthError, XDFIMError, XDFNetworkError, XDFRTCError

# ── 模型 ──
from .models import (
    LoginResult,
    StudentProfile,
    IMCredential,
    ConversationInfo,
    SendResult,
    MessageType,
    ImageInfo,
    VideoInfo,
    FileInfo,
    SystemCorrectInfo,
    CourseCardInfo,
    CallingInfo,
    ParsedMessage,
)

# ── 认证 ──
from .auth import XDFAuthClient

# ── IM ──
from .im.client import IMClient
from .im.rest import IMRestClient
from .im.bridge import IMBridgeClient
from .im.messages import (
    # 构造器
    build_text,
    build_image,
    build_video,
    build_file,
    build_system_correct,
    build_course_card,
    build_calling,
    build_offline_push,
    # 解析器
    parse_message,
    parse_message_from_bridge,
)

# ── Agora ──
from .agora import AgoraClient

# ── 白板 ──
from .whiteboard import WhiteboardSignaling

# ── 主门面 ──
from .client import XDFClient

__all__ = [
    # 环境
    "ENV_PROD", "ENV_TEST", "XDFEnvConfig",
    "IM_SDK_APP_ID", "IM_SYSTEM_USER_ID",
    # Agora 常量
    "AGORA_AUDIO_PROFILE", "AGORA_AUDIO_SCENARIO",
    "AGORA_CHANNEL_PROFILE", "AGORA_CLIENT_ROLE",
    # 异常
    "XDFError", "XDFAuthError", "XDFIMError", "XDFNetworkError", "XDFRTCError",
    # 模型
    "LoginResult", "StudentProfile", "IMCredential",
    "ConversationInfo", "SendResult",
    "MessageType", "ImageInfo", "VideoInfo", "FileInfo",
    "SystemCorrectInfo", "CourseCardInfo", "CallingInfo", "ParsedMessage",
    # 认证
    "XDFAuthClient",
    # IM
    "IMClient", "IMRestClient", "IMBridgeClient",
    "build_text", "build_image", "build_video", "build_file",
    "build_system_correct", "build_course_card", "build_calling",
    "build_offline_push",
    "parse_message", "parse_message_from_bridge",
    # RTC
    "AgoraClient",
    # 白板
    "WhiteboardSignaling",
    # 主门面
    "XDFClient",
]
