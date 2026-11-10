from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(slots=True)
class PageRedirectHop:
    from_url: str
    status_code: int
    location: str
    to_url: str


@dataclass(slots=True)
class PageHreflangAlternate:
    hreflang: str
    url: str
    source: str


@dataclass(slots=True)
class PageStructuredDataNode:
    """One top-level JSON-LD entity with property-presence facts only.

    We intentionally keep property paths rather than the full JSON-LD payload. This is enough for
    deterministic required-property checks while avoiding a second raw-content dump in the MCP
    result.
    """

    types: list[str]
    property_paths: list[str]


@dataclass(slots=True)
class PageStructuredDataBlock:
    format: str
    valid: bool
    types: list[str]
    parse_error: str | None
    nodes: list[PageStructuredDataNode] = field(default_factory=list)


@dataclass(slots=True)
class PageInspection:
    """页面当前实际交付事实。

    业务说明：这里不判断“SEO 是否优秀”，只记录浏览器/爬虫真正能拿到的 HTTP 和
    HTML 事实。SERP 中被 Google 改写后的标题、摘要不能代替这份页面事实。
    """

    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_length_bytes: int
    redirects: list[PageRedirectHop]
    title: str | None
    title_count: int
    meta_description: str | None
    meta_description_count: int
    canonical: str | None
    canonical_count: int
    robots_meta_tags: list[str]
    googlebot_meta_tags: list[str]
    declared_noindex: bool
    h1: list[str]
    lang: str | None
    charset: str | None
    meta_refresh_url: str | None
    x_robots_tags: list[str]
    hreflang_alternates: list[PageHreflangAlternate]
    anchor_links: list[str]
    rel_next_urls: list[str]
    rel_prev_urls: list[str]
    structured_data: list[PageStructuredDataBlock]
