"""
白板信令 — 通过 IM 通道传输的白板/音频控制指令。

构造与 Java WhiteBoardModule / TypeAliasProviderImpl 匹配的信令消息。

所有方法均返回可通过 IM 信令通道发送的字典对象。
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any


# 信令动作常量（来自 Java SignalAction.java）
class SignalAction:
    OPEN_AUDIO_TALK = "openAudioTalk"
    CLOSE_AUDIO_TALK = "closeAudioTalk"
    OPEN_AUDIO_TALK_MICROPHONE = "openAudioTalkMicrophone"
    CLOSE_AUDIO_TALK_MICROPHONE = "closeAudioTalkMicrophone"
    OPEN_WHITE_BOARD = "openWhiteBoard"
    CLOSE_WHITE_BOARD = "closeWhiteBoard"
    CLOSE_WHITE_BOARD_AND_AUDIO_TALK = "closeWhiteBoardAndAudioTalk"


@dataclass
class WhiteboardSignaling:
    """
    白板和音频对话的信令指令构造器。

    构造用于 Tencent IM 信令 API 的信令数据字符串:
        V2TIMSignalingManager.invite(invitee, data, ...)

    用法:
        wb = WhiteboardSignaling()
        im.send_signal(target_user="student001", data=wb.open_whiteboard(channel="room_001"))
    """

    # ── 白板控制 ──

    def open_whiteboard(self, channel: str = "", url: str = "") -> dict[str, Any]:
        """构造打开白板的信令。"""
        return {
            "action": SignalAction.OPEN_WHITE_BOARD,
            "channelId": channel,
            "url": url,
            "timestamp": _now(),
        }

    def close_whiteboard(self, channel: str = "") -> dict[str, Any]:
        """构造关闭白板的信令。"""
        return {
            "action": SignalAction.CLOSE_WHITE_BOARD,
            "channelId": channel,
            "timestamp": _now(),
        }

    def close_whiteboard_and_audio(self) -> dict[str, Any]:
        """构造关闭白板和音频对话两者的信令。"""
        return {
            "action": SignalAction.CLOSE_WHITE_BOARD_AND_AUDIO_TALK,
            "timestamp": _now(),
        }

    # ── 音频控制 ──

    def open_audio_talk(self, channel: str = "", teacher_uid: int = 0, mic_on: bool = True) -> dict[str, Any]:
        """构造打开音频对话的信令。"""
        return {
            "action": SignalAction.OPEN_AUDIO_TALK,
            "channelId": channel,
            "teacherUid": teacher_uid,
            "microphoneOn": mic_on,
            "timestamp": _now(),
        }

    def close_audio_talk(self) -> dict[str, Any]:
        """构造关闭音频对话的信令。"""
        return {
            "action": SignalAction.CLOSE_AUDIO_TALK,
            "timestamp": _now(),
        }

    # ── 麦克风控制 ──

    def microphone_on(self) -> dict[str, Any]:
        """构造打开麦克风的信令。"""
        return {
            "action": SignalAction.OPEN_AUDIO_TALK_MICROPHONE,
            "timestamp": _now(),
        }

    def microphone_off(self) -> dict[str, Any]:
        """构造关闭麦克风的信令。"""
        return {
            "action": SignalAction.CLOSE_AUDIO_TALK_MICROPHONE,
            "timestamp": _now(),
        }


def _now() -> int:
    """以毫秒为单位的当前时间戳。"""
    return int(time.time() * 1000)
