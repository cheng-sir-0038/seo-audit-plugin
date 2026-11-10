from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IndexInspection:
    """Google Search Console 中“已索引版本”的 URL Inspection 事实。

    `live_test` 在当前 V1 固定为 False：Search Console URL Inspection API 只返回 Google
    索引中已有版本的状态，不能把它当成实时抓取 / live URL test。
    """

    property_url: str
    inspection_url: str
    inspection_result_link: str | None
    verdict: str | None
    coverage_state: str | None
    robots_txt_state: str | None
    indexing_state: str | None
    last_crawl_time: str | None
    page_fetch_state: str | None
    google_canonical: str | None
    user_canonical: str | None
    crawled_as: str | None
    sitemaps: list[str] = field(default_factory=list)
    referring_urls: list[str] = field(default_factory=list)
    live_test: bool = False
