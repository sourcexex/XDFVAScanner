"""XDFLib 数据模型。"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ================================================================
#  认证模型
# ================================================================


@dataclass
class LoginResult:
    """XDF 密码登录响应。"""
    success: bool
    u2_user_id: str = ""
    u2at: str = ""
    u2at_expire: str = ""
    mobile: str = ""
    is_new_user: bool = False
    error_code: str = ""
    error_msg: str = ""


@dataclass
class StudentProfile:
    """学生档案（来自 /usercenter/v3/accounts/students）。"""
    student_code: str = ""
    school_id: str = ""
    school_name: str = ""
    student_id: str = ""
    user_id: str = ""
    real_name: str = ""
    grade_name: str = ""
    mobile: str = ""
    portrait_url: str = ""
    gender: int = 0
    age: int = 0


@dataclass
class IMCredential:
    """IM + Agora + 白板凭证（来自 /api/account/im/agora）。"""
    success: bool
    im_student_id: str = ""
    im_student_sig: str = ""
    student_code: str = ""
    agora_app_id: str = ""
    agora_token: str = ""
    agora_user_id: int = 0
    wb_user_id: str = ""
    wb_user_sign: str = ""
    error_code: str = ""
    error_msg: str = ""


# ================================================================
#  IM 模型
# ================================================================


class MessageType(Enum):
    """XDF Pad 支持的消息类型。"""
    TEXT = auto()
    IMAGE = auto()
    EMOJI = auto()
    SOUND = auto()
    VIDEO = auto()
    FILE = auto()
    CALLING = auto()
    SYSTEM_CORRECT = auto()
    COURSE_CARD = auto()
    UNKNOWN = auto()


@dataclass
class ImageInfo:
    """图片元数据（来自 TIMImageElem）。"""
    url: str = ""
    width: int = 0
    height: int = 0
    size: int = 0
    image_type: int = 0  # 0=Original, 1=Large, 2=Thumbnail, 3=Small


@dataclass
class VideoInfo:
    """视频元数据（来自 TIMVideoFileElem）。"""
    url: str = ""
    size: int = 0
    duration: int = 0  # seconds
    format: str = "mp4"
    thumb_url: str = ""
    thumb_width: int = 0
    thumb_height: int = 0


@dataclass
class FileInfo:
    """文件元数据（来自 TIMFileElem）。"""
    url: str = ""
    size: int = 0
    name: str = ""


@dataclass
class SystemCorrectInfo:
    """系统批改消息数据。"""
    title: str = ""
    content: str = ""
    scheme: str = ""


@dataclass
class CourseCardInfo:
    """课程卡片消息数据。"""
    package_name: str = ""
    res_num: str = ""
    res_type: str = "QUESTION"
    progress_total: str = "0"
    progress_complete: str = "0"
    answer_state: int = 0
    correct_state: int = 0
    answer_result: int = 0
    oral_sub_type: str | None = None


@dataclass
class CallingInfo:
    """音视频通话消息数据。"""
    duration: float = 0.0  # 0.0 = missed call

    @property
    def missed(self) -> bool:
        return self.duration <= 0.0


@dataclass
class ParsedMessage:
    """从 Tencent IM 接收的已解析消息。类型特定字段填充到对应属性中。"""
    msg_id: str = ""
    sender: str = ""
    receiver: str = ""
    timestamp: int = 0
    is_self: bool = False
    is_read: bool = False
    msg_type: MessageType = MessageType.UNKNOWN

    # Type-specific content (only one is non-None based on msg_type)
    text: str = ""
    images: list[ImageInfo] = field(default_factory=list)
    is_emoji: bool = False
    sound_url: str = ""
    sound_size: int = 0
    sound_duration: int = 0
    video: VideoInfo | None = None
    file: FileInfo | None = None
    correct: SystemCorrectInfo | None = None
    course: CourseCardInfo | None = None
    call: CallingInfo | None = None

    # Raw data for custom messages
    custom_business_id: str = ""
    custom_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationInfo:
    """从会话列表 API 获取的会话摘要。"""
    user_id: str = ""
    nickname: str = ""
    avatar_url: str = ""
    last_message: ParsedMessage | None = None
    unread_count: int = 0
    is_system: bool = False


@dataclass
class SendResult:
    """消息发送结果。"""
    success: bool
    msg_key: str = ""
    msg_time: int = 0
    error_code: int = 0
    error_info: str = ""
