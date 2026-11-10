from __future__ import annotations

from enum import StrEnum


class SeoDataErrorCode(StrEnum):
    """跨 Provider 稳定的数据层错误语义。"""

    NOT_CONFIGURED = "not_configured"
    AUTHORIZATION_REQUIRED = "authorization_required"
    AUTHORIZATION_TIMEOUT = "authorization_timeout"
    PERMISSION_DENIED = "permission_denied"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    INVALID_MARKET_INPUT = "invalid_market_input"
    DATA_UNAVAILABLE = "data_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_MARKET_UNAVAILABLE = "provider_market_unavailable"
    UNSUPPORTED_FOR_CAPABILITY = "unsupported_for_capability"
    ACCESS_FORBIDDEN = "access_forbidden"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"


class SeoDataError(RuntimeError):
    """公共数据层错误。

    上层 Skill 不理解 Google、Semrush 等供应商自己的错误码。Client/Adapter 先把上游
    错误转换成 `SeoDataErrorCode`，MCP Boundary 再序列化为稳定字符串。
    """

    def __init__(self, code: SeoDataErrorCode, message: str) -> None:
        if not isinstance(code, SeoDataErrorCode):
            raise TypeError("SeoDataError code must be SeoDataErrorCode")
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}
