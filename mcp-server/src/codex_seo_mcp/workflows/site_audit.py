from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from codex_seo_mcp.adapters.page_inspection import PageInspectionAdapter
from codex_seo_mcp.adapters.resource_inspection import ResourceInspectionAdapter
from codex_seo_mcp.errors import SeoDataError


async def inspect_site_basics(
    url: str,
    page_inspection: PageInspectionAdapter,
    resource_inspection: ResourceInspectionAdapter,
) -> dict[str, Any]:
    """Collect one page, robots.txt and at most one same-origin sitemap."""
    page = await page_inspection.inspect(url)
    target = urlsplit(page.data.final_url)
    origin = urlunsplit((target.scheme, target.netloc, "/", "", ""))
    robots_url = urljoin(origin, "robots.txt")
    limitations = [
        "仅检查一个页面和最多一个 sitemap，不代表整站抓取。",
        "页面 HTML 不包含 JavaScript 渲染结果，也不能证明 Google 抓取或收录状态。",
    ]
    partial = not 200 <= page.data.status_code < 300
    declared: list[str] = []
    try:
        robots_result = await resource_inspection.inspect(robots_url, resource_type="robots")
        robots = robots_result.to_dict()
        if not _same_origin(robots_result.data.final_url, origin):
            limitations.append("robots.txt 发生跨站重定向，未采用其中的 sitemap 声明。")
            partial = True
        elif 200 <= robots_result.data.status_code < 300 and robots_result.data.robots:
            declared = robots_result.data.robots.sitemaps
        else:
            partial = True
    except SeoDataError as exc:
        robots = {"status": "failed", "error": exc.to_dict()}
        partial = True

    candidates: list[str] = []
    for item in declared:
        try:
            candidates.append(urljoin(robots_url, item))
        except ValueError:
            limitations.append("robots.txt 中有无效 sitemap 地址，无法检查。")
            partial = True
    same_origin = [item for item in candidates if _same_origin(item, origin)]
    if len(same_origin) != len(candidates):
        limitations.append("robots.txt 声明了跨站 sitemap，本流程不会自动访问。")
        partial = True
    if len(same_origin) > 1:
        limitations.append("robots.txt 声明了多个 sitemap，本流程只检查第一个同站地址。")
        partial = True
    # shortcut: inspect one same-origin sitemap; expand when multi-sitemap coverage is needed.
    sitemap_url = same_origin[0] if same_origin else urljoin(origin, "sitemap.xml")
    entry_count: int | None = None
    try:
        sitemap_result = await resource_inspection.inspect(sitemap_url, resource_type="sitemap")
        sitemap = sitemap_result.to_dict()
        partial |= not 200 <= sitemap_result.data.status_code < 300
        if not _same_origin(sitemap_result.data.final_url, origin):
            limitations.append("sitemap 发生跨站重定向，结果来自其他站点。")
            partial = True
        entries = sitemap["data"]["sitemap"]["entries"]
        entry_count = len(entries)
        if entry_count > 20:
            sitemap["data"]["sitemap"]["entries"] = entries[:20]
            limitations.append("sitemap 结果仅展示前 20 条；总数为本次解析到的条数。")
    except SeoDataError as exc:
        sitemap = {"status": "failed", "error": exc.to_dict()}
        partial = True

    return {
        "status": "partial" if partial else "complete",
        "page": page.to_dict(),
        "robots": robots,
        "sitemap": sitemap,
        "sitemap_entry_count": entry_count,
        "limitations": limitations,
    }


def _same_origin(url: str, origin: str) -> bool:
    target, expected = urlsplit(url), urlsplit(origin)
    return (target.scheme.lower(), target.netloc.lower()) == (
        expected.scheme.lower(), expected.netloc.lower()
    )
