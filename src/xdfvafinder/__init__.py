"""XDFVAScanner — XDF 账号安全扫描器。

子模块:
- ``xdfvafinder.scanner``      按号段批量扫描可登录账号
- ``xdfvafinder.debug_login``  单账号登录调试

协议库 ``xdflib`` 以源码形式内置在 ``src/xdflib``，随本项目一起安装，
因此本项目只依赖公开的 PyPI 包即可运行。
"""

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

__all__ = ["LoginOutcome", "Scanner", "__version__"]

if TYPE_CHECKING:
    from .scanner import LoginOutcome, Scanner


def __getattr__(name: str) -> Any:
    """按需导入扫描器。

    顶层不做 eager import，这样 ``python -m xdfvafinder.scanner`` 不会触发
    runpy 的 "found in sys.modules after import of package" 警告。
    """
    if name == "Scanner":
        from .scanner import Scanner

        return Scanner
    if name == "LoginOutcome":
        from .scanner import LoginOutcome

        return LoginOutcome
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
