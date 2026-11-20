"""XDF 环境配置 — 生产 & 测试环境的 API 地址和加密密钥。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class XDFEnvConfig:
    """XDF 服务的环境特定配置。"""
    name: str
    login_api: str
    gateway_api: str
    user_center_api: str
    app_id: str
    app_secret: str
    u2_app_id: str
    u2_app_key: str
    u2_en32_key: str
    t3_id: str
    ehr_org_id: str


# ================================================================
#  从 APK AccountConfigUtils.java 提取的已硬编码密钥
# ================================================================

ENV_PROD = XDFEnvConfig(
    name="PROD",
    login_api="https://loginapi.xdf.cn",
    gateway_api="https://npad-api.xdf.cn",
    user_center_api="https://gateway.xdf.cn",
    app_id="npad",
    app_secret="07f7eaaa0d858797ab9b2af553facd77",
    u2_app_id="970077",
    u2_app_key="u2a_b80a70ff93af45bfabc383772d2df9c8",
    u2_en32_key="u2en32key_a3335f8ad7544e7a9fb9eb",
    t3_id="appupoc",
    ehr_org_id="105",
)

ENV_TEST = XDFEnvConfig(
    name="TEST",
    login_api="https://loginapi-t.test.xdf.cn",
    gateway_api="https://ckai-npad-api-test1.test.xdf.cn",
    user_center_api="https://gateway.test.xdf.cn",
    app_id="npad20220630",
    app_secret="d4307bc84b79ef67fa08fbb7bc19b87a",
    u2_app_id="998142",
    u2_app_key="test_u2a_a2c3664a22824ffcaf492aeaee39d82e",
    u2_en32_key="test_u2en32key_86c520c95cad41a5b",
    t3_id="appupoc",
    ehr_org_id="105",
)

# 腾讯 IM SDK 常量（来自 BuildConfig.java）
IM_SDK_APP_ID = 1400695484
IM_SYSTEM_USER_ID = "system_push"

# Agora 音频配置常量（来自 RtcEngineManager.java）
AGORA_AUDIO_PROFILE = 0       # AUDIO_PROFILE_DEFAULT（语音标准）
AGORA_AUDIO_SCENARIO = 3      # AUDIO_SCENARIO_GAME_STREAMING（低延迟）
AGORA_CHANNEL_PROFILE = 1     # CHANNEL_PROFILE_LIVE_BROADCASTING
AGORA_CLIENT_ROLE = 1         # CLIENT_ROLE_BROADCASTER

# XDF Pad 应用元数据
APP_VERSION = "1.2.0"
APP_DEVICE_PLATFORM = "APP"
APP_DEVICE_TYPE = "ANDROID_MOBILE"
