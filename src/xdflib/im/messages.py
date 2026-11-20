"""
IM 消息构造器 & 解析器。

支持 XDF Pad 的所有 8 种消息类型（5 种标准 + 3 种自定义），
以及图像、视频和文件附件。

消息构造器生成 Tencent IM REST API MsgBody 格式。
解析器处理 REST API 响应和 Bridge 事件两种格式。
"""

import json as _json
import logging
import time
from typing import Any

from ..models import (
    CallingInfo,
    CourseCardInfo,
    FileInfo,
    ImageInfo,
    MessageType,
    ParsedMessage,
    SystemCorrectInfo,
    VideoInfo,
)

logger = logging.getLogger("xdflib.im.messages")

# 已知自定义消息 businessID 常量（来自 IMBussinessConstant.java）
_BUSINESS_ID_CALLING = "custom_calling"
_BUSINESS_ID_SYSTEM_CORRECT = "system_correct"
_BUSINESS_ID_COURSE_CARD = "custom_course_card"

# REST API MsgType 字符串 → 元素类型整数映射
_MSG_TYPE_MAP: dict[str, int] = {
    "TIMTextElem": 1,
    "TIMCustomElem": 2,
    "TIMImageElem": 3,
    "TIMSoundElem": 4,
    "TIMVideoFileElem": 5,
    "TIMFileElem": 6,
}

# ================================================================
#  消息构造器（返回 MsgBody 列表用于 REST API / Bridge 发送）
# ================================================================


def build_text(text: str) -> list[dict[str, Any]]:
    """构造文本消息 MsgBody。"""
    return [{"MsgType": "TIMTextElem", "MsgContent": {"Text": text}}]


def build_image(
    image_url: str,
    *,
    width: int = 0,
    height: int = 0,
    image_format: int = 1,
    size: int = 0,
) -> list[dict[str, Any]]:
    """构造图片消息 MsgBody（REST API — 需要可公开访问的 URL）。"""
    return [{
        "MsgType": "TIMImageElem",
        "MsgContent": {
            "UUID": "",
            "ImageFormat": image_format,
            "ImageInfoArray": [{
                "Type": 1,  # Original
                "Size": size,
                "Width": width,
                "Height": height,
                "URL": image_url,
            }],
        },
    }]


def build_video(
    video_url: str,
    *,
    video_size: int = 0,
    video_second: int = 0,
    video_format: str = "mp4",
    thumb_url: str = "",
    thumb_size: int = 0,
    thumb_width: int = 0,
    thumb_height: int = 0,
) -> list[dict[str, Any]]:
    """构造视频消息 MsgBody（REST API — 需要可公开访问的 URL）。"""
    return [{
        "MsgType": "TIMVideoFileElem",
        "MsgContent": {
            "VideoUrl": video_url,
            "VideoSize": video_size,
            "VideoSecond": video_second,
            "VideoFormat": video_format,
            "VideoDownloadFlag": 2,  # 允许下载
            "ThumbUrl": thumb_url,
            "ThumbSize": thumb_size,
            "ThumbWidth": thumb_width,
            "ThumbHeight": thumb_height,
            "ThumbDownloadFlag": 2,
        },
    }]


def build_file(
    file_url: str,
    *,
    file_size: int = 0,
    file_name: str = "",
) -> list[dict[str, Any]]:
    """构造文件消息 MsgBody（REST API — 需要可公开访问的 URL）。"""
    return [{
        "MsgType": "TIMFileElem",
        "MsgContent": {
            "FileUrl": file_url,
            "FileSize": file_size,
            "FileName": file_name,
            "FileDownloadFlag": 2,
        },
    }]


def build_system_correct(
    message_title: str,
    message_content: str,
    scheme: str = "xdf://learning/correct",
) -> list[dict[str, Any]]:
    """构造系统批改通知消息（custom: businessID=system_correct）。"""
    inner = {
        "message_title": message_title,
        "message_content": message_content,
        "scheme": scheme,
    }
    outer = {
        "businessID": _BUSINESS_ID_SYSTEM_CORRECT,
        "data": _json.dumps(inner, ensure_ascii=False),
    }
    return [{
        "MsgType": "TIMCustomElem",
        "MsgContent": {
            "Data": _json.dumps(outer, ensure_ascii=False),
            "Desc": message_title,
            "Ext": "",
        },
    }]


def build_course_card(
    package_name: str,
    *,
    res_num: str = "",
    res_type: str = "QUESTION",
    progress_total: str = "0",
    progress_complete: str = "0",
    answer_state: int = 0,
    correct_state: int = 0,
    answer_result: int = 0,
    oral_sub_type: str | None = None,
) -> list[dict[str, Any]]:
    """构造课程卡片消息（custom: businessID=custom_course_card）。"""
    inner: dict[str, Any] = {
        "package_name": package_name,
        "res_num": res_num,
        "res_type": res_type,
        "progress_total": progress_total,
        "progress_complete": progress_complete,
        "answer_state": answer_state,
        "correct_state": correct_state,
        "answer_result": answer_result,
    }
    if oral_sub_type:
        inner["oral_sub_type"] = oral_sub_type

    outer = {
        "businessID": _BUSINESS_ID_COURSE_CARD,
        "data": _json.dumps(inner, ensure_ascii=False),
        "description": package_name,
        "version": 0,
    }
    return [{
        "MsgType": "TIMCustomElem",
        "MsgContent": {
            "Data": _json.dumps(outer, ensure_ascii=False),
            "Desc": package_name,
            "Ext": "",
        },
    }]


def build_calling(call_duration: float = 0.0) -> list[dict[str, Any]]:
    """构造音视频通话消息（custom: businessID=custom_calling）。"""
    inner = {"call_duration": call_duration}
    outer = {
        "businessID": _BUSINESS_ID_CALLING,
        "data": _json.dumps(inner, ensure_ascii=False),
    }
    desc = f"通话时长 {call_duration:.0f}秒" if call_duration > 0 else "未接来电"
    return [{
        "MsgType": "TIMCustomElem",
        "MsgContent": {
            "Data": _json.dumps(outer, ensure_ascii=False),
            "Desc": desc,
            "Ext": "",
        },
    }]


def build_offline_push(
    sender: str,
    nickname: str,
    content: str,
) -> dict[str, Any]:
    """构造离线推送信息，匹配 APK OfflinePushInfoUtils 格式。"""
    entity = {
        "entity": {
            "version": 1,
            "chatType": 1,       # C2C
            "action": 1,         # CHAT
            "sender": sender,
            "nickname": nickname,
            "faceUrl": "",
            "content": content,
            "sendTime": int(time.time() * 1000),
        },
    }
    return {
        "PushFlag": 0,
        "Title": nickname,
        "Desc": content[:50],
        "Ext": _json.dumps(entity, ensure_ascii=False),
        "AndroidInfo": {"OPPOChannelID": "tuikit"},
    }


# ================================================================
#  消息解析器
# ================================================================


def _parse_custom_data(custom_bytes: str | bytes) -> dict[str, Any]:
    """将自定义数据字节解析为带有 businessID + 数据字段的字典。"""
    if isinstance(custom_bytes, bytes):
        custom_bytes = custom_bytes.decode("utf-8", errors="replace")
    try:
        return _json.loads(custom_bytes)
    except (_json.JSONDecodeError, TypeError):
        return {}


def _elem_type_to_message_type(elem_type: int, custom: dict | None = None) -> MessageType:
    """
    将 Tencent IM 元素类型映射到 XDF 消息类型。
    对于自定义消息（类型 2），检查 businessID 进行二次分类。

    参考: IMMessageBean.getMessageType()
    """
    if elem_type == 1:
        return MessageType.TEXT
    elif elem_type == 3:
        # 检查 image 是否实际上是 emoji（cloudCustomData 中有 KEY_EMOJIS_IMG 标记）
        if custom and custom.get("is_emoji"):
            return MessageType.EMOJI
        return MessageType.IMAGE
    elif elem_type == 4:
        return MessageType.SOUND
    elif elem_type == 5:
        return MessageType.VIDEO
    elif elem_type == 2:
        if not custom:
            return MessageType.UNKNOWN
        bid = custom.get("businessID", "")
        if bid == _BUSINESS_ID_CALLING:
            return MessageType.CALLING
        elif bid == _BUSINESS_ID_SYSTEM_CORRECT:
            return MessageType.SYSTEM_CORRECT
        elif bid == _BUSINESS_ID_COURSE_CARD:
            return MessageType.COURSE_CARD
        return MessageType.UNKNOWN
    elif elem_type == 6:
        return MessageType.FILE
    return MessageType.UNKNOWN


def parse_message(raw: dict[str, Any]) -> ParsedMessage:
    """
    将 Tencent IM REST API 响应消息解析为 ParsedMessage。

    参数:
        raw: 来自 REST API 的原始消息对象（例如来自 admin_getroammsg 或 sendmsg 响应）。

    返回:
        已解析的强类型 ParsedMessage。
    """
    msg = ParsedMessage(
        msg_id=raw.get("MsgKey", raw.get("MsgId", "")),
        sender=raw.get("From_Account", raw.get("From", "")),
        receiver=raw.get("To_Account", raw.get("To", "")),
        timestamp=raw.get("MsgTimestamp", raw.get("MsgTime", 0)),
        is_self=raw.get("IsPlaceMsg", 0) == 1,
        is_read=False,
    )

    msg_body = raw.get("MsgBody", [])
    if not msg_body:
        return msg

    first = msg_body[0]
    msg_type_str = first.get("MsgType", "")
    content = first.get("MsgContent", {})

    # 将 REST API 的 MsgType 字符串映射到元素类型整数
    elem_type = _MSG_TYPE_MAP.get(msg_type_str, -1)
    custom = None

    if elem_type == 1:  # 文本
        msg.msg_type = MessageType.TEXT
        msg.text = content.get("Text", "")

    elif elem_type == 2:  # 自定义
        raw_data = content.get("Data", "")
        custom = _parse_custom_data(raw_data)
        msg.msg_type = _elem_type_to_message_type(2, custom)
        msg.custom_business_id = custom.get("businessID", "")
        msg.custom_data = custom

        if msg.msg_type == MessageType.SYSTEM_CORRECT:
            inner_str = custom.get("data", "")
            try:
                inner = _json.loads(inner_str) if isinstance(inner_str, str) else inner_str
                msg.correct = SystemCorrectInfo(
                    title=inner.get("message_title", ""),
                    content=inner.get("message_content", ""),
                    scheme=inner.get("scheme", ""),
                )
            except (_json.JSONDecodeError, TypeError):
                pass

        elif msg.msg_type == MessageType.CALLING:
            inner_str = custom.get("data", "")
            try:
                inner = _json.loads(inner_str) if isinstance(inner_str, str) else inner_str
                msg.call = CallingInfo(duration=inner.get("call_duration", 0.0))
            except (_json.JSONDecodeError, TypeError):
                pass

        elif msg.msg_type == MessageType.COURSE_CARD:
            inner_str = custom.get("data", "")
            try:
                inner = _json.loads(inner_str) if isinstance(inner_str, str) else inner_str
                msg.course = CourseCardInfo(
                    package_name=inner.get("package_name", ""),
                    res_num=inner.get("res_num", ""),
                    res_type=inner.get("res_type", "QUESTION"),
                    progress_total=inner.get("progress_total", "0"),
                    progress_complete=inner.get("progress_complete", "0"),
                    answer_state=inner.get("answer_state", 0),
                    correct_state=inner.get("correct_state", 0),
                    answer_result=inner.get("answer_result", 0),
                    oral_sub_type=inner.get("oral_sub_type"),
                )
            except (_json.JSONDecodeError, TypeError):
                pass

    elif elem_type == 3:  # 图片
        msg.msg_type = MessageType.IMAGE
        for info in content.get("ImageInfoArray", []):
            msg.images.append(ImageInfo(
                url=info.get("URL", ""),
                width=info.get("Width", 0),
                height=info.get("Height", 0),
                size=info.get("Size", 0),
                image_type=info.get("Type", 0),
            ))

    elif elem_type == 4:  # 语音
        msg.msg_type = MessageType.SOUND
        msg.sound_url = content.get("Url", "")
        msg.sound_size = content.get("Size", 0)
        msg.sound_duration = content.get("Second", 0)

    elif elem_type == 5:  # 视频
        msg.msg_type = MessageType.VIDEO
        msg.video = VideoInfo(
            url=content.get("VideoUrl", ""),
            size=content.get("VideoSize", 0),
            duration=content.get("VideoSecond", 0),
            format=content.get("VideoFormat", "mp4"),
            thumb_url=content.get("ThumbUrl", ""),
            thumb_width=content.get("ThumbWidth", 0),
            thumb_height=content.get("ThumbHeight", 0),
        )

    elif elem_type == 6:  # 文件
        msg.msg_type = MessageType.FILE
        msg.file = FileInfo(
            url=content.get("FileUrl", ""),
            size=content.get("FileSize", 0),
            name=content.get("FileName", ""),
        )

    return msg


def parse_message_from_bridge(data: dict[str, Any]) -> ParsedMessage:
    """
    从 Node.js Bridge 事件数据解析消息。

    Bridge 发出 {event: "message", data: {id, type, from, to, time, payload: {...}}}。
    type 字段使用 TencentCloudChat TYPES 字符串（例如 "TIMTextElem"、"TIMCustomElem"）。
    """
    msg = ParsedMessage(
        msg_id=data.get("id", ""),
        sender=data.get("from", ""),
        receiver=data.get("to", ""),
        timestamp=data.get("time", 0),
        is_self=False,
    )

    msg_type_str = data.get("type", "")
    payload = data.get("payload", {})

    if msg_type_str == "TIMTextElem":
        msg.msg_type = MessageType.TEXT
        msg.text = payload.get("text", "")
    elif msg_type_str == "TIMImageElem":
        msg.msg_type = MessageType.IMAGE
        for info in payload.get("imageInfoArray", payload.get("imageDataArray", [])):
            msg.images.append(ImageInfo(
                url=info.get("URL", info.get("url", "")),
                width=info.get("Width", info.get("width", 0)),
                height=info.get("Height", info.get("height", 0)),
                size=info.get("Size", info.get("size", 0)),
                image_type=info.get("type", 0),
            ))
    elif msg_type_str == "TIMVideoFileElem":
        msg.msg_type = MessageType.VIDEO
        msg.video = VideoInfo(
            url=payload.get("videoUrl", payload.get("VideoUrl", "")),
            size=payload.get("videoSize", payload.get("VideoSize", 0)),
            duration=payload.get("videoSecond", payload.get("VideoSecond", 0)),
            format=payload.get("videoFormat", payload.get("VideoFormat", "mp4")),
            thumb_url=payload.get("thumbUrl", payload.get("ThumbUrl", "")),
        )
    elif msg_type_str == "TIMFileElem":
        msg.msg_type = MessageType.FILE
        msg.file = FileInfo(
            url=payload.get("fileUrl", payload.get("FileUrl", "")),
            size=payload.get("fileSize", payload.get("FileSize", 0)),
            name=payload.get("fileName", payload.get("FileName", "")),
        )
    elif msg_type_str == "TIMSoundElem":
        msg.msg_type = MessageType.SOUND
        msg.sound_url = payload.get("url", "")
        msg.sound_duration = payload.get("second", 0)
    elif msg_type_str == "TIMCustomElem":
        custom_str = payload.get("data", "")
        custom = _parse_custom_data(custom_str)
        msg.msg_type = _elem_type_to_message_type(2, custom)
        msg.custom_business_id = custom.get("businessID", "")
        msg.custom_data = custom
        # 递归解析内部数据
        inner_str = custom.get("data", "")
        try:
            inner = _json.loads(inner_str) if isinstance(inner_str, str) else inner_str
        except (_json.JSONDecodeError, TypeError):
            inner = {}

        if msg.msg_type == MessageType.SYSTEM_CORRECT:
            msg.correct = SystemCorrectInfo(
                title=inner.get("message_title", ""),
                content=inner.get("message_content", ""),
                scheme=inner.get("scheme", ""),
            )
        elif msg.msg_type == MessageType.CALLING:
            msg.call = CallingInfo(duration=inner.get("call_duration", 0.0))
        elif msg.msg_type == MessageType.COURSE_CARD:
            msg.course = CourseCardInfo(
                package_name=inner.get("package_name", ""),
                res_num=inner.get("res_num", ""),
                res_type=inner.get("res_type", "QUESTION"),
                progress_total=inner.get("progress_total", "0"),
                progress_complete=inner.get("progress_complete", "0"),
                answer_state=inner.get("answer_state", 0),
                correct_state=inner.get("correct_state", 0),
                answer_result=inner.get("answer_result", 0),
            )

    return msg
