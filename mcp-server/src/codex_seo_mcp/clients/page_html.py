from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode

Resolver = Callable[[str], Awaitable[list[str]]]
HTTP_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass(slots=True)
class PageHtmlConfig:
    """公开页面抓取边界配置。

    超时、响应大小和重定向上限既是资源保护，也是产品稳定性边界，防止异常页面让一次
    SEO 调查无限占用 Agent 任务时间。
    """

    request_timeout_seconds: float = 15.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_redirects: int = 5
    user_agent: str = "CodexSEO/0.1 PageInspection"


@dataclass(slots=True)
class RawHttpResponse:
    """Transport 层最小 HTTP 结果，不在这里解释 SEO 语义。"""

    status_code: int
    headers: dict[str, str]
    body: bytes
    header_values: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class FetchedRedirectHop:
    """Transport 层实际观察到的一跳 HTTP Redirect。"""

    from_url: str
    status_code: int
    location: str
    to_url: str


@dataclass(slots=True)
class FetchedPage:
    """完成重定向和安全校验后的页面抓取结果。"""

    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_length_bytes: int
    redirects: list[FetchedRedirectHop]
    headers: dict[str, str]
    html: str
    header_values: dict[str, list[str]] = field(default_factory=dict)


class HttpTransport(Protocol):
    """HTTP 实现 seam，方便测试时用假的网络响应验证业务边界。"""

    async def get(self, url: str, *, config: PageHtmlConfig) -> RawHttpResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    """关闭 urllib 自动跳转，让每一次跳转都重新经过安全边界检查。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibTransport:
    """基于标准库的默认 HTTP Transport。"""

    async def get(self, url: str, *, config: PageHtmlConfig) -> RawHttpResponse:
        return await asyncio.to_thread(self._get_sync, url, config)

    @staticmethod
    def _get_sync(url: str, config: PageHtmlConfig) -> RawHttpResponse:
        opener = build_opener(_NoRedirect())
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "User-Agent": config.user_agent,
            },
        )
        try:
            with opener.open(request, timeout=config.request_timeout_seconds) as response:
                status = int(response.status)
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                header_values = _collect_header_values(response.headers)
                body = _read_limited(response, config.max_response_bytes)
                return RawHttpResponse(status, headers, body, header_values=header_values)
        except HTTPError as exc:
            # 业务说明：关闭自动重定向后，urllib 会把 3xx 作为 HTTPError 抛出；
            # 它仍然是有效 HTTP 响应，需要继续读取 Location 后自行处理。
            headers = {str(k).lower(): str(v) for k, v in exc.headers.items()}
            header_values = _collect_header_values(exc.headers)
            body = _read_limited(exc, config.max_response_bytes)
            return RawHttpResponse(int(exc.code), headers, body, header_values=header_values)
        except URLError as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"页面请求失败：{exc.reason}") from exc
        except TimeoutError as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "页面请求超时") from exc


def _read_limited(response, limit: int) -> bytes:  # noqa: ANN001
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "页面 HTML 响应超过大小限制")
        chunks.append(bytes(chunk))
    return b"".join(chunks)


async def default_resolver(host: str) -> list[str]:
    """解析域名全部地址，供 SSRF 边界检查使用。

    不能只验证用户输入的 hostname 字符串，因为公开域名也可能解析到 localhost、私网
    或云 metadata 地址。
    """

    def _resolve() -> list[str]:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            if item[4]
        }
        return sorted(addresses)

    try:
        return await asyncio.to_thread(_resolve)
    except socket.gaierror as exc:
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"无法解析目标域名：{host}") from exc


class PageHtmlClient:
    """受 SSRF 边界保护的公开页面抓取客户端。

    业务说明：这个 Client 未来可能运行在开发者电脑或企业网络中，所以“能发 HTTP
    请求”不等于“允许访问任何地址”。它只服务公开站点 PageInspection。
    """

    def __init__(
        self,
        *,
        config: PageHtmlConfig | None = None,
        resolver: Resolver = default_resolver,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config or PageHtmlConfig()
        self.resolver = resolver
        self.transport = transport or UrllibTransport()

    async def fetch(self, url: str) -> FetchedPage:
        """抓取页面，并显式处理每一跳重定向。"""

        requested = _normalize_url(url)
        current = requested
        redirects: list[FetchedRedirectHop] = []

        for redirect_count in range(self.config.max_redirects + 1):
            # 安全边界：公开 URL 工具不能因为运行在用户机器/公司网络里，就获得访问
            # localhost、云 metadata 或企业内网的隐式能力；每一次重定向都重新校验。
            await self._assert_public_target(current)
            response = await self.transport.get(current, config=self.config)

            location = response.headers.get("location")
            if response.status_code in HTTP_REDIRECT_STATUS_CODES and location:
                if redirect_count >= self.config.max_redirects:
                    raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "页面重定向次数超过限制")
                next_url = _normalize_url(urljoin(current, location))
                redirects.append(
                    FetchedRedirectHop(
                        from_url=current,
                        status_code=response.status_code,
                        location=location,
                        to_url=next_url,
                    )
                )
                current = next_url
                continue

            content_type = response.headers.get("content-type")
            media_type = (content_type or "").split(";", 1)[0].strip().lower()
            if media_type not in {"text/html", "application/xhtml+xml"}:
                raise SeoDataError(SeoDataErrorCode.DATA_UNAVAILABLE, "目标 URL 返回的不是 HTML 页面")

            charset = _charset_from_content_type(content_type) or "utf-8"
            try:
                html = response.body.decode(charset, errors="replace")
            except LookupError:
                html = response.body.decode("utf-8", errors="replace")

            return FetchedPage(
                requested_url=requested,
                final_url=current,
                status_code=response.status_code,
                content_type=content_type,
                content_length_bytes=len(response.body),
                redirects=redirects,
                headers=response.headers,
                html=html,
                header_values=(
                    response.header_values
                    or {key: [value] for key, value in response.headers.items()}
                ),
            )

        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "页面重定向处理失败")

    async def _assert_public_target(self, url: str) -> None:
        """确认当前 URL 解析到的所有地址都属于可访问公网范围。"""

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise SeoDataError(SeoDataErrorCode.ACCESS_FORBIDDEN, "PageInspection 默认不允许访问本机或私有网络")

        addresses = [host] if _looks_like_ip(host) else await self.resolver(host)
        if not addresses:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"目标域名没有可用地址：{host}")
        if any(_is_private_address(address) for address in addresses):
            raise SeoDataError(SeoDataErrorCode.ACCESS_FORBIDDEN, "PageInspection 默认不允许访问本机或私有网络")


def _normalize_url(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "url 不能为空")
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    try:
        port = parsed.port
    except ValueError as exc:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "url 端口无效") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in {None, 80, 443}
    ):
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "url 必须是有效的 HTTP/HTTPS 公网页面地址")
    return parsed._replace(path=parsed.path or "/", fragment="").geturl()


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_private_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _charset_from_content_type(content_type: str | None) -> str | None:
    for part in (content_type or "").split(";")[1:]:
        key, separator, value = part.partition("=")
        if separator and key.strip().lower() == "charset":
            return value.strip().strip("\"'") or None
    return None


def _collect_header_values(headers) -> dict[str, list[str]]:  # noqa: ANN001
    """保留重复 HTTP header；普通 dict 只能保存其中一个值。"""

    names = {str(name).lower() for name in headers.keys()}
    result: dict[str, list[str]] = {}
    for name in names:
        values = headers.get_all(name) or headers.get_all(name.title()) or []
        normalized = [str(value) for value in values]
        if normalized:
            result[name] = normalized
    return result
