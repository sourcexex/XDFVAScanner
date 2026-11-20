"""XDFLib 自定义异常层级。"""


class XDFError(Exception):
    """所有 XDFLib 异常的基类。"""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {super().__str__()}"
        return super().__str__()


class XDFAuthError(XDFError):
    """认证失败（登录凭证无效、Token 过期、IM 凭证缺失）。"""
    pass


class XDFIMError(XDFError):
    """IM 操作失败（发送失败、连接中断、用户未登录）。"""
    pass


class XDFNetworkError(XDFError):
    """网络错误（超时、DNS 解析失败、连接被拒）。"""
    pass


class XDFRTCError(XDFError):
    """Agora RTC 操作失败（Token 生成、频道加入）。"""
    pass
