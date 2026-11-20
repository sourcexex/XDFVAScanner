"""
XDFClient 主门面 — 将认证、IM、Agora 和白板整合为一个统一接口。

用法:
    from xdflib import XDFClient, ENV_PROD

    with XDFClient(env="PROD") as c:
        c.login(mobile="138...", password="...")
        c.connect_im(mode="bridge")
        c.im.on_message = lambda msg: print(msg)
        c.im.send_text(to="student_id", text="你好！")
        c.agora.generate_token(channel="lesson_001", uid=12345)
"""

import logging
from types import SimpleNamespace
from typing import Any

from .auth import XDFAuthClient
from .config import ENV_PROD, ENV_TEST, XDFEnvConfig, IM_SDK_APP_ID
from .im.client import IMClient
from .im.base import IMBaseClient
from .agora import AgoraClient
from .whiteboard import WhiteboardSignaling
from .models import IMCredential, LoginResult, StudentProfile

logger = logging.getLogger("xdflib.client")


def _get_env(name: str) -> XDFEnvConfig:
    """将环境名称解析为 XDFEnvConfig。"""
    name_upper = name.upper()
    if name_upper == "PROD":
        return ENV_PROD
    elif name_upper in ("TEST", "T"):
        return ENV_TEST
    else:
        raise ValueError(f"未知环境: {name}。有效选项: PROD、TEST")


class XDFClient:
    """
    主 XDF Pad 通信客户端。

    连接认证、IM、Agora RTC 和白板信令。
    支持 REST API 和 Bridge 两种 IM 模式。

    上下文管理器用法:
        with XDFClient(env="PROD") as client:
            client.login(mobile="...", password="...")
            client.connect_im(mode="bridge")
            client.im.send_text(to="student", text="你好")

    手动用法:
        client = XDFClient(env="PROD")
        client.login(mobile="...", password="...")
        client.connect_im(mode="rest", secret_key="...")
        ...
        client.disconnect()
    """

    def __init__(self, env: str | XDFEnvConfig = "PROD"):
        if isinstance(env, str):
            env = _get_env(env)
        self.env = env
        self.auth = XDFAuthClient(env=env)

        # 会话状态
        self._login_result: LoginResult | None = None
        self._credential: IMCredential | None = None
        self._students: list[StudentProfile] = []

        # 子模块（连接后可用）
        self._im: IMBaseClient | None = None
        self.agora = AgoraClient()
        self.wb = WhiteboardSignaling()

    # ── 属性 ──

    @property
    def im(self) -> IMBaseClient:
        """IM 客户端（连接前为 None）。"""
        if self._im is None:
            raise RuntimeError("未连接 IM。请先调用 connect_im()")
        return self._im

    @property
    def is_logged_in(self) -> bool:
        return self._login_result is not None and self._login_result.success

    @property
    def is_connected(self) -> bool:
        return self._im is not None

    @property
    def current_student(self) -> StudentProfile | None:
        return self._students[0] if self._students else None

    # ── 认证 ──

    def login(
        self,
        mobile: str,
        password: str,
        *,
        student_code: str = "",
    ) -> tuple[LoginResult, IMCredential | None, list[StudentProfile]]:
        """
        完整登录流程：登录 → 获取学生 → 获取 IM 凭证。

        成功时将凭证存储在 self._credential 中并配置子模块。
        """
        result, cred, students = self.auth.login_and_fetch_im(
            mobile, password, student_code=student_code
        )
        self._login_result = result
        self._credential = cred
        self._students = students

        if cred and cred.success:
            # 使用来自 IM 凭证的 Agora 凭证配置 Agora
            self.agora = AgoraClient(
                app_id=cred.agora_app_id,
            )

        return result, cred, students

    # ── IM 连接 ──

    def connect_im(
        self,
        mode: str = "auto",
        *,
        sdk_app_id: int = IM_SDK_APP_ID,
        secret_key: str = "",
        **kwargs,
    ) -> IMBaseClient:
        """
        根据可用凭证连接到 IM。

        参数:
            mode: "rest"、"bridge" 或 "auto"（默认）。
            sdk_app_id: Tencent IM SDK App ID。
            secret_key: REST API 模式的管理员密钥。
            **kwargs: 传递给 IMClient.rest() 或 IMClient.bridge() 的额外参数。

        mode="bridge" 时，需要先调用 login() 获取 IM 凭证。
        """
        if mode == "rest":
            self._im = IMClient.rest(sdk_app_id=sdk_app_id, secret_key=secret_key, **kwargs)
        elif mode == "bridge":
            if not self._credential:
                raise RuntimeError("Bridge 模式需要 IM 凭证。请先调用 login()")
            self._im = IMClient.bridge(
                sdk_app_id=sdk_app_id,
                user_id=self._credential.im_student_id,
                user_sig=self._credential.im_student_sig,
                **kwargs,
            )
            # 连接到 Node.js 桥接
            self._im.connect()
        elif mode == "auto":
            if secret_key:
                self._im = IMClient.rest(sdk_app_id=sdk_app_id, secret_key=secret_key, **kwargs)
            elif self._credential:
                self._im = IMClient.bridge(
                    sdk_app_id=sdk_app_id,
                    user_id=self._credential.im_student_id,
                    user_sig=self._credential.im_student_sig,
                    **kwargs,
                )
                self._im.connect()
            else:
                raise RuntimeError(
                    "无法确定 IM 模式。请提供 secret_key（REST 模式）或先调用 login()（Bridge 模式）"
                )
        else:
            raise ValueError(f"未知 IM 模式: {mode}。有效选项: rest、bridge、auto")

        logger.info("已连接到 IM（模式=%s）", mode)
        return self._im

    def disconnect(self) -> None:
        """断开所有连接。"""
        if self._im and hasattr(self._im, 'disconnect'):
            self._im.disconnect()
        self._im = None

    # ── 上下文管理器 ──

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect()
