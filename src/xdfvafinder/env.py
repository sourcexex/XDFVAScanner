"""环境解析：把命令行里的 ``test`` / ``prod`` 映射到 xdflib 的环境配置。"""

from xdflib import ENV_PROD, ENV_TEST, XDFEnvConfig

ENV_CHOICES: tuple[str, ...] = ("test", "prod")

_BY_NAME: dict[str, XDFEnvConfig] = {"test": ENV_TEST, "prod": ENV_PROD}

__all__ = ["ENV_CHOICES", "env_name", "resolve_env"]


def resolve_env(name: str) -> XDFEnvConfig:
    """把环境名解析为 xdflib 的 :class:`XDFEnvConfig`；未知名称抛 ``ValueError``。"""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ValueError(f"未知环境 {name!r}，可选: {', '.join(ENV_CHOICES)}") from None


def env_name(config: XDFEnvConfig) -> str:
    """把环境配置反查回 ``test`` / ``prod``（写断点时用）。"""
    return config.name.lower()
