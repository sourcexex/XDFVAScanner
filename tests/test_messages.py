"""Tests for message builders and parsers."""

import json

from xdflib.im.messages import (
    build_calling,
    build_course_card,
    build_file,
    build_image,
    build_system_correct,
    build_text,
    build_video,
    parse_message,
)
from xdflib.models import MessageType


class TestBuildText:
    def test_simple(self):
        msg = build_text("Hello World")
        assert len(msg) == 1
        assert msg[0]["MsgType"] == "TIMTextElem"
        assert msg[0]["MsgContent"]["Text"] == "Hello World"


class TestBuildImage:
    def test_url_based(self):
        msg = build_image("https://example.com/img.jpg", width=800, height=600)
        assert len(msg) == 1
        assert msg[0]["MsgType"] == "TIMImageElem"
        info = msg[0]["MsgContent"]["ImageInfoArray"][0]
        assert info["URL"] == "https://example.com/img.jpg"
        assert info["Width"] == 800
        assert info["Height"] == 600


class TestBuildVideo:
    def test_url_based(self):
        msg = build_video("https://example.com/vid.mp4", video_second=120, video_size=5000000)
        content = msg[0]["MsgContent"]
        assert content["VideoUrl"] == "https://example.com/vid.mp4"
        assert content["VideoSecond"] == 120


class TestBuildFile:
    def test_url_based(self):
        msg = build_file("https://example.com/doc.pdf", file_size=1024, file_name="doc.pdf")
        content = msg[0]["MsgContent"]
        assert content["FileUrl"] == "https://example.com/doc.pdf"
        assert content["FileName"] == "doc.pdf"


class TestBuildCustomMessages:
    def test_system_correct(self):
        msg = build_system_correct("批改", "内容", "xdf://app")
        outer = json.loads(msg[0]["MsgContent"]["Data"])
        assert outer["businessID"] == "system_correct"
        inner = json.loads(outer["data"])
        assert inner["message_title"] == "批改"

    def test_course_card(self):
        msg = build_course_card("数学课", res_type="QUESTION")
        outer = json.loads(msg[0]["MsgContent"]["Data"])
        assert outer["businessID"] == "custom_course_card"

    def test_calling(self):
        msg = build_calling(call_duration=125.0)
        outer = json.loads(msg[0]["MsgContent"]["Data"])
        assert outer["businessID"] == "custom_calling"
        inner = json.loads(outer["data"])
        assert inner["call_duration"] == 125.0


class TestParseMessage:
    def test_parse_text(self):
        raw = {
            "MsgKey": "msg_001",
            "From_Account": "user_a",
            "To_Account": "user_b",
            "MsgTimestamp": 1700000000,
            "MsgBody": [{"MsgType": "TIMTextElem", "MsgContent": {"Text": "Hello"}}],
        }
        parsed = parse_message(raw)
        assert parsed.msg_type == MessageType.TEXT
        assert parsed.text == "Hello"
        assert parsed.sender == "user_a"

    def test_parse_system_correct(self):
        inner = json.dumps({"message_title": "批改", "message_content": "done", "scheme": "xdf://"})
        outer = json.dumps({"businessID": "system_correct", "data": inner})
        raw = {
            "MsgKey": "msg_002",
            "From_Account": "system_push",
            "MsgTimestamp": 1700000000,
            "MsgBody": [{"MsgType": "TIMCustomElem", "MsgContent": {"Data": outer}}],
        }
        parsed = parse_message(raw)
        assert parsed.msg_type == MessageType.SYSTEM_CORRECT
        assert parsed.correct is not None
        assert parsed.correct.title == "批改"

    def test_parse_calling(self):
        inner = json.dumps({"call_duration": 45.0})
        outer = json.dumps({"businessID": "custom_calling", "data": inner})
        raw = {
            "MsgKey": "msg_003",
            "From_Account": "teacher",
            "MsgTimestamp": 1700000000,
            "MsgBody": [{"MsgType": "TIMCustomElem", "MsgContent": {"Data": outer}}],
        }
        parsed = parse_message(raw)
        assert parsed.msg_type == MessageType.CALLING
        assert parsed.call is not None
        assert parsed.call.duration == 45.0
        assert not parsed.call.missed

    def test_parse_image(self):
        raw = {
            "MsgKey": "msg_004",
            "From_Account": "user_a",
            "MsgTimestamp": 1700000000,
            "MsgBody": [
                {
                    "MsgType": "TIMImageElem",
                    "MsgContent": {
                        "ImageInfoArray": [
                            {"URL": "https://x.cn/a.jpg", "Width": 800, "Height": 600}
                        ]
                    },
                }
            ],
        }
        parsed = parse_message(raw)
        assert parsed.msg_type == MessageType.IMAGE
        assert len(parsed.images) == 1
        assert parsed.images[0].url == "https://x.cn/a.jpg"
