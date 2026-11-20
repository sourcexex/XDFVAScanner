"""
IM 客户端门面 — 根据配置自动选择 REST 或 Bridge 传输。

用法:
    # REST 模式（需要管理员密钥）
    im = IMClient.rest(sdk_app_id=1400695484, secret_key="...")

    # Bridge 模式（实时双向）
    im = IMClient.bridge(sdk_app_id=1400695484, user_id="...", user_sig="...")
"""

from ..config import IM_SDK_APP_ID
from .base import IMBaseClient
from .rest import IMRestClient
from .bridge import IMBridgeClient


class IMClient:
    """
    IM 客户端门面。

    不直接实例化。使用类方法选择传输方式:
    - IMClient.rest(...) → IMRestClient
    - IMClient.bridge(...) → IMBridgeClient
    """

    @staticmethod
    def rest(
        sdk_app_id: int = IM_SDK_APP_ID,
        secret_key: str = "",
        *,
        admin_identifier: str = "administrator",
    ) -> IMRestClient:
        """创建 REST API 客户端（需要管理员 secret_key）。"""
        return IMRestClient(
            sdk_app_id=sdk_app_id,
            secret_key=secret_key,
            admin_identifier=admin_identifier,
        )

    @staticmethod
    def bridge(
        sdk_app_id: int = IM_SDK_APP_ID,
        *,
        user_id: str = "",
        user_sig: str = "",
    ) -> IMBridgeClient:
        """创建 SDK Bridge 客户端（实时双向，需要 Node.js）。"""
        return IMBridgeClient(
            sdk_app_id=sdk_app_id,
            user_id=user_id,
            user_sig=user_sig,
        )

    @staticmethod
    def auto(
        sdk_app_id: int = IM_SDK_APP_ID,
        *,
        secret_key: str = "",
        user_id: str = "",
        user_sig: str = "",
    ) -> IMBaseClient:
        """
        根据提供的凭证自动选择传输方式。

        如果提供了 secret_key → REST 模式。
        如果提供了 user_id + user_sig → Bridge 模式。
        """
        if secret_key:
            return IMClient.rest(sdk_app_id=sdk_app_id, secret_key=secret_key)
        elif user_id and user_sig:
            return IMClient.bridge(sdk_app_id=sdk_app_id, user_id=user_id, user_sig=user_sig)
        else:
            raise ValueError("必须提供 secret_key（REST 模式）或 user_id+user_sig（Bridge 模式）")
