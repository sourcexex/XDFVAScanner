"""
腾讯云 IM REST API 客户端。

需要来自腾讯云 IM 控制台的管理员 secret_key。
使用 TLSSigAPIv2 对管理员请求进行认证。
"""

import logging
import random
import time

import requests

from ..config import IM_SDK_APP_ID
from ..models import ConversationInfo, ParsedMessage, SendResult
from ..tls_sig import gen_admin_user_sig
from .base import IMBaseClient
from .messages import parse_message

logger = logging.getLogger("xdflib.im.rest")


class IMRestClient(IMBaseClient):
    """
    用于管理员端操作的腾讯云 IM REST API 客户端。

    Base URL: https://console.tim.qq.com/v4/{service}/{command}
        ?sdkappid={id}&identifier={admin}&usersig={sig}&random={r}&contenttype=json
    """

    BASE_URL = "https://console.tim.qq.com"

    def __init__(
        self,
        sdk_app_id: int = IM_SDK_APP_ID,
        secret_key: str = "",
        *,
        admin_identifier: str = "administrator",
        expire_seconds: int = 15552000,  # 180 天
    ):
        super().__init__(sdk_app_id)
        self.secret_key = secret_key
        self.admin_identifier = admin_identifier
        self.expire_seconds = expire_seconds

        if not secret_key:
            logger.warning("secret_key 未配置；REST API 调用将失败")

        self._admin_sig: str = ""
        self._admin_sig_time: float = 0.0

    # ── UserSig 缓存 ──

    def _get_admin_sig(self) -> str:
        """获取或刷新管理员 UserSig（缓存 1 小时）。"""
        now = time.time()
        if self._admin_sig and (now - self._admin_sig_time) < 3600:
            return self._admin_sig

        self._admin_sig = gen_admin_user_sig(
            self.sdk_app_id, self.secret_key,
            self.admin_identifier, self.expire_seconds,
        )
        self._admin_sig_time = now
        logger.debug("已刷新管理员 UserSig")
        return self._admin_sig

    def _build_url(self, service: str, command: str) -> str:
        """构造带签名查询参数的 REST API URL。"""
        sig = self._get_admin_sig()
        rand = random.randint(0, 0x7FFFFFFF)
        return (
            f"{self.BASE_URL}/v4/{service}/{command}"
            f"?sdkappid={self.sdk_app_id}"
            f"&identifier={self.admin_identifier}"
            f"&usersig={sig}"
            f"&random={rand}"
            f"&contenttype=json"
        )

    def _post(self, service: str, command: str, body: dict) -> dict:
        """向 REST API 发送 POST 请求。"""
        url = self._build_url(service, command)
        logger.debug("POST %s...", url[:100])
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"ActionStatus": "FAIL", "ErrorCode": -1, "ErrorInfo": "Timeout"}
        except requests.exceptions.RequestException as e:
            return {"ActionStatus": "FAIL", "ErrorCode": -1, "ErrorInfo": str(e)}
        except ValueError:
            return {"ActionStatus": "FAIL", "ErrorCode": -2, "ErrorInfo": "Invalid JSON"}

    def _check_result(self, result: dict) -> SendResult:
        """将 REST API 响应字典转换为 SendResult。"""
        err_code = result.get("ErrorCode", -1)
        if err_code == 0:
            return SendResult(
                success=True,
                msg_key=result.get("MsgKey", ""),
                msg_time=result.get("MsgTime", 0),
            )
        else:
            return SendResult(
                success=False,
                error_code=err_code,
                error_info=result.get("ErrorInfo", "Unknown error"),
            )

    # ── 发送 ──

    def send_msg(
        self,
        from_account: str,
        to_account: str,
        msg_body: list[dict],
        *,
        offline_push_info: dict | None = None,
        msg_life_time: int = 604800,
    ) -> SendResult:
        body: dict = {
            "SyncOtherMachine": 2,
            "From_Account": from_account,
            "To_Account": to_account,
            "MsgLifeTime": msg_life_time,
            "MsgRandom": random.randint(0, 0x7FFFFFFF),
            "MsgBody": msg_body,
        }
        if offline_push_info:
            body["OfflinePushInfo"] = offline_push_info

        result = self._post("openim", "sendmsg", body)
        return self._check_result(result)

    def batch_send_msg(
        self,
        from_account: str,
        to_accounts: list[str],
        msg_body: list[dict],
        *,
        msg_life_time: int = 604800,
    ) -> SendResult:
        body = {
            "SyncOtherMachine": 2,
            "From_Account": from_account,
            "To_Account": to_accounts,
            "MsgRandom": random.randint(0, 0x7FFFFFFF),
            "MsgBody": msg_body,
            "MsgLifeTime": msg_life_time,
        }
        result = self._post("openim", "batchsendmsg", body)
        return self._check_result(result)

    # ── 拉取 ──

    def fetch_history(
        self,
        user_id: str,
        count: int = 20,
        last_msg_key: str | None = None,
    ) -> list[ParsedMessage]:
        """
        通过 REST API 拉取漫游消息。

        注意：这是管理员端 API（admin_getroammsg）。
        它从任意两个用户之间拉取服务器端消息历史。
        """
        body: dict = {
            "From_Account": user_id,
            "To_Account": self.admin_identifier,
            "MaxCnt": min(count, 200),
        }
        if last_msg_key:
            body["LastMsgKey"] = last_msg_key

        result = self._post("openim", "admin_getroammsg", body)
        if result.get("ErrorCode") != 0:
            logger.error("拉取历史失败: %s", result.get("ErrorInfo", ""))
            return []

        messages: list[ParsedMessage] = []
        for raw in result.get("MsgList", []):
            try:
                messages.append(parse_message(raw))
            except Exception as e:
                logger.warning("解析历史消息失败: %s", e)
        return messages

    def fetch_conversations(self) -> list[ConversationInfo]:
        """通过 REST API 获取最近联系人。"""
        body = {"From_Account": self.admin_identifier, "Count": 100}
        result = self._post("recentcontact", "get_list", body)
        if result.get("ErrorCode") != 0:
            return []

        conversations: list[ConversationInfo] = []
        for raw in result.get("ContactItem", []):
            conv_type = raw.get("Type", 1)
            if conv_type != 1:  # 仅 C2C
                continue
            conversations.append(ConversationInfo(
                user_id=raw.get("To_Account", ""),
                unread_count=raw.get("UnreadCount", 0),
            ))
        return conversations

    # ── 账号管理 ──

    def account_import(self, user_id: str, nick: str = "", face_url: str = "") -> SendResult:
        body = {"UserID": user_id, "Nick": nick, "FaceUrl": face_url}
        result = self._post("im_open_login_svc", "account_import", body)
        return self._check_result(result)
