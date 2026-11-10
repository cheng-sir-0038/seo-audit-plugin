from __future__ import annotations

from urllib.parse import urlsplit

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


def normalize_page_quality_url(value: str) -> str:
    """Validate one target before either performance provider receives it."""

    if not isinstance(value, str) or not value.strip():
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测 URL 不能为空")
    text = value.strip()
    if any(ord(char) < 32 for char in text):
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测 URL 包含无效字符")
    if "://" not in text:
        text = f"https://{text}"
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测 URL 格式或端口无效") from exc
    if parsed.scheme not in {"http", "https"} or not hostname or any(char.isspace() for char in hostname):
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测只支持有效的 HTTP/HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测不接受 URL 内嵌账号或密码")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        authority += f":{port}"
    return parsed._replace(netloc=authority, path=parsed.path or "/", fragment="").geturl()
