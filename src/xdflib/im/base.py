"""IM 抽象基类 — 定义发送/接收/查询的统一接口。"""

from abc import ABC, abstractmethod
from typing import Callable

from ..models import ConversationInfo, ParsedMessage, SendResult, MessageType


MessageCallback = Callable[[ParsedMessage], None]
"""收到消息时调用的回调函数签名。"""


class IMBaseClient(ABC):
    """IM 客户端抽象基类。REST 和 Bridge 传输都继承此类。"""

    def __init__(self, sdk_app_id: int):
        self.sdk_app_id = sdk_app_id
        self._on_message: MessageCallback | None = None

    @property
    def on_message(self) -> MessageCallback | None:
        """当前消息回调（仅 Bridge 模式支持实时回调）。"""
        return self._on_message

    @on_message.setter
    def on_message(self, callback: MessageCallback | None) -> None:
        self._on_message = callback

    # ── 发送 ──

    @abstractmethod
    def send_msg(
        self,
        from_account: str,
        to_account: str,
        msg_body: list[dict],
        *,
        offline_push_info: dict | None = None,
        msg_life_time: int = 604800,
    ) -> SendResult:
        """发送 C2C 消息（原始 MsgBody）。"""
        ...

    @abstractmethod
    def batch_send_msg(
        self,
        from_account: str,
        to_accounts: list[str],
        msg_body: list[dict],
        *,
        msg_life_time: int = 604800,
    ) -> SendResult:
        """批量发送 C2C 消息。"""
        ...

    # ── 历史 & 查询 ──

    @abstractmethod
    def fetch_history(
        self,
        user_id: str,
        count: int = 20,
        last_msg_key: str | None = None,
    ) -> list[ParsedMessage]:
        """拉取与用户的 C2C 消息历史。"""
        ...

    @abstractmethod
    def fetch_conversations(self) -> list[ConversationInfo]:
        """获取会话列表。"""
        ...

    @abstractmethod
    def account_import(self, user_id: str, nick: str = "", face_url: str = "") -> SendResult:
        """将用户导入 IM 系统。"""
        ...

    # ── 便捷方法 ──

    def send_text(
        self,
        to: str,
        text: str,
        from_user: str = "",
        *,
        nickname: str = "教师",
    ) -> SendResult:
        """发送文本消息。"""
        from .messages import build_text, build_offline_push
        msg = build_text(text)
        push = build_offline_push(from_user or "admin", nickname, text)
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)

    def send_image_url(
        self,
        to: str,
        url: str,
        from_user: str = "",
        *,
        width: int = 0,
        height: int = 0,
        nickname: str = "教师",
    ) -> SendResult:
        """通过 URL 发送图片消息（REST API 模式）。"""
        from .messages import build_image, build_offline_push
        msg = build_image(url, width=width, height=height)
        push = build_offline_push(from_user or "admin", nickname, "[图片]")
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)

    def send_video_url(
        self,
        to: str,
        url: str,
        from_user: str = "",
        *,
        duration: int = 0,
        size: int = 0,
        thumb_url: str = "",
        nickname: str = "教师",
    ) -> SendResult:
        """通过 URL 发送视频消息（REST API 模式）。"""
        from .messages import build_video, build_offline_push
        msg = build_video(url, video_second=duration, video_size=size, thumb_url=thumb_url)
        push = build_offline_push(from_user or "admin", nickname, "[视频]")
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)

    def send_system_correct(
        self,
        to: str,
        title: str,
        content: str,
        from_user: str = "",
        *,
        scheme: str = "xdf://learning/correct",
        nickname: str = "系统通知",
    ) -> SendResult:
        """发送系统批改消息。"""
        from .messages import build_system_correct, build_offline_push
        msg = build_system_correct(title, content, scheme)
        push = build_offline_push(from_user or "admin", nickname, title)
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)

    def send_course_card(
        self,
        to: str,
        package_name: str,
        from_user: str = "",
        *,
        res_type: str = "QUESTION",
        res_num: str = "",
        progress_total: str = "0",
        progress_complete: str = "0",
        nickname: str = "课程通知",
        **kwargs,
    ) -> SendResult:
        """发送课程卡片消息。"""
        from .messages import build_course_card, build_offline_push
        msg = build_course_card(
            package_name=package_name,
            res_num=res_num,
            res_type=res_type,
            progress_total=progress_total,
            progress_complete=progress_complete,
            **kwargs,
        )
        push = build_offline_push(from_user or "admin", nickname, package_name)
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)

    def send_calling(
        self,
        to: str,
        from_user: str = "",
        *,
        call_duration: float = 0.0,
        nickname: str = "语音通话",
    ) -> SendResult:
        """发送音视频通话消息。"""
        from .messages import build_calling, build_offline_push
        msg = build_calling(call_duration)
        desc = f"通话 {call_duration:.0f}秒" if call_duration > 0 else "未接来电"
        push = build_offline_push(from_user or "admin", nickname, desc)
        return self.send_msg(from_user or "admin", to, msg, offline_push_info=push)
