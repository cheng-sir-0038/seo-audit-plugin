from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    getproxies,
    proxy_bypass,
    urlopen,
)

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

    async def get(
        self, url: str, *, config: PageHtmlConfig, pinned_addresses: list[str] | None = None
    ) -> RawHttpResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    """关闭 urllib 自动跳转，让每一次跳转都重新经过安全边界检查。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibTransport:
    """基于标准库的默认 HTTP Transport。"""

    async def get(
        self, url: str, *, config: PageHtmlConfig, pinned_addresses: list[str] | None = None
    ) -> RawHttpResponse:
        if pinned_addresses is not None:
            return await asyncio.to_thread(self._get_pinned_sync, url, config, pinned_addresses)
        return await asyncio.to_thread(self._get_sync, url, config)

    @staticmethod
    def _get_pinned_sync(
        url: str, config: PageHtmlConfig, addresses: list[str]
    ) -> RawHttpResponse:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not addresses or any(_is_private_address(address) for address in addresses):
            raise SeoDataError(SeoDataErrorCode.ACCESS_FORBIDDEN, "目标地址不是公网地址")
        if getproxies().get(parsed.scheme) and not proxy_bypass(host):
            # shortcut: no pinned proxy tunnel; add one if explicit proxy support is needed.
            raise SeoDataError(
                SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                "Fake-IP 环境中的显式 HTTP 代理暂不支持安全固定目标地址。",
            )
        deadline = time.monotonic() + config.request_timeout_seconds
        last_error: Exception | None = None
        for address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            connection_type = (
                http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
            )
            connection = connection_type(host, port=parsed.port, timeout=remaining)
            # Keep the original host for HTTP Host and TLS SNI while connecting to a verified IP.
            connection._create_connection = (
                lambda target, timeout, source_address, ip=address: socket.create_connection(
                    (ip, target[1]), timeout, source_address
                )
            )
            try:
                path = parsed.path or "/"
                if parsed.query:
                    path += f"?{parsed.query}"
                connection.request("GET", path, headers={
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                    "User-Agent": config.user_agent,
                })
                response = connection.getresponse()
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                header_values = _collect_header_values(response.headers)
                body = _read_limited(response, config.max_response_bytes)
                return RawHttpResponse(int(response.status), headers, body, header_values)
            except (OSError, http.client.HTTPException) as exc:
                last_error = exc
            finally:
                connection.close()
        raise SeoDataError(
            SeoDataErrorCode.PROVIDER_UNAVAILABLE, "无法连接经过校验的公网地址"
        ) from last_error

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


async def resolve_fake_ip(host: str) -> list[str]:
    """Resolve public A/AAAA records when the system supplies a Fake-IP address."""
    # shortcut: one public DNS service; add configurable providers if it is unavailable.
    answers = await asyncio.gather(*(
        asyncio.to_thread(_query_public_dns, host, record_type) for record_type in ("A", "AAAA")
    ))
    addresses = list(dict.fromkeys(address for group in answers for address in group))
    if not addresses:
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "公网 DNS 未返回目标地址")
    return addresses


def _query_public_dns(host: str, record_type: str) -> list[str]:
    query = urlencode({"name": host, "type": record_type})
    request = Request(f"https://dns.google/resolve?{query}", headers={"Accept": "application/dns-json"})
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read(65_537)
        if len(body) > 65_536:
            raise ValueError("DNS response too large")
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("Status") != 0:
            raise ValueError("DNS lookup unsuccessful")
        expected_type = 1 if record_type == "A" else 28
        return [
            str(item["data"])
            for item in data.get("Answer", [])
            if isinstance(item, dict) and item.get("type") == expected_type and "data" in item
        ]
    except (OSError, ValueError, TypeError) as exc:
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "公网 DNS 查询失败") from exc


async def validate_public_target(
    url: str, resolver: Resolver, *, capability: str
) -> list[str] | None:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa"))
        or ("." not in host and not _looks_like_ip(host))
    ):
        raise SeoDataError(SeoDataErrorCode.ACCESS_FORBIDDEN, f"{capability} 默认不允许访问本机或私有网络")
    literal = _looks_like_ip(host)
    addresses = [host] if literal else await resolver(host)
    if not addresses:
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"目标域名没有可用地址：{host}")

    # Fake-IP is only a proxy placeholder; direct requests must use verified public addresses.
    fallback = not literal and all(_is_fake_ip(address) for address in addresses)
    if fallback:
        addresses = await resolve_fake_ip(host)
    if not addresses or any(_is_private_address(address) for address in addresses):
        raise SeoDataError(SeoDataErrorCode.ACCESS_FORBIDDEN, f"{capability} 默认不允许访问本机或私有网络")
    return addresses if fallback else None


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
            pinned = await self._assert_public_target(current)
            response = (
                await self.transport.get(current, config=self.config, pinned_addresses=pinned)
                if pinned is not None else await self.transport.get(current, config=self.config)
            )

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

    async def _assert_public_target(self, url: str) -> list[str] | None:
        """确认当前 URL 解析到的所有地址都属于可访问公网范围。"""
        return await validate_public_target(url, self.resolver, capability="PageInspection")


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
    return not address.is_global or address.is_multicast


def _is_fake_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value) in ipaddress.ip_network("198.18.0.0/15")
    except ValueError:
        return False


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
