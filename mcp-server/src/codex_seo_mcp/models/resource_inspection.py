from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RobotsRule:
    directive: str
    path: str


@dataclass(slots=True)
class RobotsGroup:
    user_agents: list[str] = field(default_factory=list)
    rules: list[RobotsRule] = field(default_factory=list)


@dataclass(slots=True)
class RobotsResource:
    groups: list[RobotsGroup] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SitemapEntry:
    loc: str
    lastmod: str | None = None


@dataclass(slots=True)
class SitemapResource:
    kind: str
    entries: list[SitemapEntry] = field(default_factory=list)


@dataclass(slots=True)
class ResourceInspection:
    """robots.txt 或 sitemap 的 SEO 资源事实。

    这不是通用 HTTP fetch 结果；V1 只承载 crawl/index diagnosis 需要的 robots 与
    sitemap 结构，避免把任意文本/XML 下载能力塞进 SEO Core。
    """

    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_length_bytes: int
    redirect_chain: list[str]
    resource_type: str
    robots: RobotsResource | None = None
    sitemap: SitemapResource | None = None
