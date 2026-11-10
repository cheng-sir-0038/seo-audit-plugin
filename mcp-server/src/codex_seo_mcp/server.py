from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, Resolve

from codex_seo_mcp.diagnosis.rich_results import assess_rich_results
from codex_seo_mcp.observability import observe_tool
from codex_seo_mcp.runtime import build_runtime
from codex_seo_mcp.scope_resolution import (
    Ga4PropertyCandidates,
    Ga4ResolvedScope,
    GscPropertyCandidates,
    GscResolvedScope,
    PropertyChoice,
    choose_ga4_property,
    choose_gsc_property,
    finalize_ga4_scope,
    finalize_gsc_scope,
    match_ga4_properties_for_domain,
    resolve_ga4_candidates,
    resolve_gsc_candidates,
)
from codex_seo_mcp.tool_boundary import map_seo_data_errors
from codex_seo_mcp.tool_metadata import (
    EXTERNAL_AUTHORIZATION_ACTION,
    READ_ONLY_LOCAL,
    READ_ONLY_OPEN_WORLD,
)
from codex_seo_mcp.workflows.site_audit import inspect_site_basics as run_site_basics

mcp = MCPServer(
    "Codex SEO",
    instructions=(
        "提供通用 SEO 数据能力。工具返回页面、搜索和研究数据事实，不替代 Product Skill 的诊断判断。"
    ),
)

_runtime = build_runtime()
_gsc = _runtime.gsc
_ga4 = _runtime.ga4
_page_inspection = _runtime.page_inspection
_index_inspection = _runtime.index_inspection
_resource_inspection = _runtime.resource_inspection
_page_quality = _runtime.page_quality
_search_performance = _runtime.search_performance
_keyword_research = _runtime.keyword_research
_organic_visibility = _runtime.organic_visibility
_competitor_research = _runtime.competitor_research
_serp_research = _runtime.serp_research
_site_safety = _runtime.site_safety
_web_analytics = _runtime.web_analytics


async def _resolve_gsc_candidates(target: str) -> GscPropertyCandidates:
    return await resolve_gsc_candidates(_gsc, target)


def _choose_gsc_property(
    candidates: Annotated[GscPropertyCandidates, Resolve(_resolve_gsc_candidates)],
) -> PropertyChoice | Elicit[PropertyChoice]:
    return choose_gsc_property(candidates)


def _resolve_gsc_scope(
    candidates: Annotated[GscPropertyCandidates, Resolve(_resolve_gsc_candidates)],
    choice: Annotated[PropertyChoice, Resolve(_choose_gsc_property)],
) -> GscResolvedScope:
    return finalize_gsc_scope(candidates, choice)


async def _resolve_gsc_candidates_for_inspection(inspection_url: str) -> GscPropertyCandidates:
    return await resolve_gsc_candidates(_gsc, inspection_url)


def _choose_gsc_property_for_inspection(
    candidates: Annotated[
        GscPropertyCandidates, Resolve(_resolve_gsc_candidates_for_inspection)
    ],
) -> PropertyChoice | Elicit[PropertyChoice]:
    return choose_gsc_property(candidates)


def _resolve_gsc_scope_for_inspection(
    candidates: Annotated[
        GscPropertyCandidates, Resolve(_resolve_gsc_candidates_for_inspection)
    ],
    choice: Annotated[PropertyChoice, Resolve(_choose_gsc_property_for_inspection)],
) -> GscResolvedScope:
    return finalize_gsc_scope(candidates, choice)


async def _resolve_ga4_candidates(target: str) -> Ga4PropertyCandidates:
    return await resolve_ga4_candidates(_ga4, target)


def _choose_ga4_property(
    candidates: Annotated[Ga4PropertyCandidates, Resolve(_resolve_ga4_candidates)],
) -> PropertyChoice | Elicit[PropertyChoice]:
    return choose_ga4_property(candidates)


def _resolve_ga4_scope(
    candidates: Annotated[Ga4PropertyCandidates, Resolve(_resolve_ga4_candidates)],
    choice: Annotated[PropertyChoice, Resolve(_choose_ga4_property)],
) -> Ga4ResolvedScope:
    return finalize_ga4_scope(candidates, choice)


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="页面 SEO 检查")
@observe_tool(tool="inspect_page", capability="PageInspection", target_arg="url")
@map_seo_data_errors
async def inspect_page(url: str) -> dict[str, Any]:
    """读取公开网页的 HTTP/HTML SEO 事实。

    业务边界：返回 Title、Canonical、Robots、H1、重定向等页面事实；不根据这些字段
    自动下最终 SEO 结论，也不访问 localhost、私网或云 metadata 地址。
    """

    return (await _page_inspection.inspect(url)).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="网站 SEO 基础检查")
@observe_tool(tool="inspect_site_basics", target_arg="url")
@map_seo_data_errors
async def inspect_site_basics(url: str) -> dict[str, Any]:
    """只读检查一个页面、robots.txt 和最多一个同站 sitemap。

    返回各项事实和失败原因；不等于整站爬取，也不能证明 Google 收录状态。
    """
    return await run_site_basics(url, _page_inspection, _resource_inspection)


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="富媒体结果检查")
@observe_tool(tool="check_rich_results", target_arg="url")
@map_seo_data_errors
async def check_rich_results(
    url: str,
    expected_types: list[str] | None = None,
) -> dict[str, Any]:
    """检查当前页面 JSON-LD 与已维护 Google Rich Result required-property 规则。

    该 Tool 复用 PageInspection 的运行时结构化数据事实，不抓取 Rich Results Test 网页，
    也不把“必需属性通过”表述成 Google 一定展示富媒体结果。
    """

    page_result = await _page_inspection.inspect(url)
    assessment = assess_rich_results(
        page_result.data,
        expected_types=expected_types,
    )
    return {
        "status": "complete",
        "source_kind": "derived",
        "data": assessment.to_dict(),
        "warnings": [],
    }


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="网站安全检查")
@observe_tool(
    tool="check_site_safety",
    capability="SiteSafety",
    target_arg="url",
)
@map_seo_data_errors
async def check_site_safety(url: str) -> dict[str, Any]:
    """检查公开 URL 是否命中当前恶意网址 Provider 的已知威胁列表。

    当前个人/非商业 Provider 是 Google Safe Browsing v4 Lookup。无匹配只表示“未发现已知威胁”，
    不代表绝对安全；未来商业分发应在同一 SiteSafety Contract 下切换到 Web Risk。
    """

    return (await _site_safety.check(url)).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="Google 收录检查")
@observe_tool(
    tool="inspect_google_index",
    capability="IndexInspection",
    target_arg="inspection_url",
)
@map_seo_data_errors
async def inspect_google_index(
    inspection_url: str,
    scope: Annotated[GscResolvedScope, Resolve(_resolve_gsc_scope_for_inspection)],
    language_code: str = "en-US",
) -> dict[str, Any]:
    """读取 Google 索引中的 URL Inspection 状态。

    Search Console Property 由 `inspection_url` 在 Tool 执行前自动解析；存在多个同等有效候选时
    通过 elicitation 要求用户选择，模型不能直接指定隐藏 Property。
    返回 Google 已索引版本的 coverage、robots、indexing、crawl、canonical 等事实。
    这不是 live URL test，也不替代 PageInspection 的当前 HTTP/HTML 事实。
    """

    return (
        await _index_inspection.inspect(
            property_url=scope.property_url,
            inspection_url=inspection_url,
            language_code=language_code,
        )
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="Robots / Sitemap 检查")
@observe_tool(tool="inspect_robots_sitemap", capability="ResourceInspection", target_arg="url")
@map_seo_data_errors
async def inspect_robots_sitemap(
    url: str,
    resource_type: str = "auto",
) -> dict[str, Any]:
    """检查 robots.txt 或 sitemap 的运行时 SEO 资源事实。

    只解析 crawl/index diagnosis 需要的 robots groups、Allow/Disallow、Sitemap 声明、
    sitemap URL/sitemap-index entries；不是通用 HTTP/XML 下载工具。
    """

    return (
        await _resource_inspection.inspect(url, resource_type=resource_type)
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="页面性能检查")
@observe_tool(
    tool="check_page_performance",
    capability="PageQuality",
    target_arg="url",
    strategy_arg="strategy",
)
@map_seo_data_errors
async def check_page_performance(
    url: str,
    strategy: str,
    locale: str = "zh-CN",
) -> dict[str, Any]:
    """读取页面性能与体验数据。

    实验室检测来自 Google PageSpeed Insights/Lighthouse，真实用户体验来自 CrUX。
    两边都拿到时返回 complete；任一数据源无数据或不可用时保留另一边并返回 partial。
    Lighthouse 分数不是 Google 自然搜索排名分数，CrUX Origin fallback 也不能伪装成当前 URL 自身数据。
    """

    return (
        await _page_quality.inspect(url, strategy=strategy, locale=locale)
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_LOCAL, title="Search Console 连接状态")
@observe_tool(tool="check_search_console_connection")
async def check_search_console_connection() -> dict[str, str]:
    """查看 GSC OAuth 状态；未配置/未授权时返回可执行的下一步，不触发浏览器。"""

    return await _gsc.connection_status()


@mcp.tool(annotations=EXTERNAL_AUTHORIZATION_ACTION, title="连接 Search Console")
@observe_tool(tool="connect_search_console")
@map_seo_data_errors
async def connect_search_console() -> dict[str, Any]:
    """显式发起 Google Search Console Desktop OAuth。

    该 Tool 会打开系统浏览器并启动 Google OAuth，因此由 Agent Host 的原生 Tool Approval
    决定是否允许执行；Plugin 不再叠加 form elicitation 二次确认。
    """

    return await _gsc.authorize()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="Search Console 站点列表")
@observe_tool(tool="list_search_console_sites")
@map_seo_data_errors
async def list_search_console_sites(target: str | None = None) -> dict[str, Any]:
    """列出可访问的 Search Console Properties，并可按 domain/URL 解析目标 Property。

    该 Tool 只负责显式列出/排障。分析 Tool 自己通过 hidden dependency 解析 Property；这里的列表顺序不是默认选择。
    """

    if not target:
        return {"status": "complete", "properties": await _gsc.list_properties()}

    matched_properties = await _gsc.resolve_properties_for_target(target)
    match_status = (
        "matched"
        if len(matched_properties) == 1
        else "ambiguous"
        if len(matched_properties) > 1
        else "not_found"
    )
    return {
        "status": "complete",
        "target": target,
        "match_status": match_status,
        "matched_properties": matched_properties,
    }


@mcp.tool(annotations=READ_ONLY_LOCAL, title="GA4 连接状态")
@observe_tool(tool="check_analytics_connection")
async def check_analytics_connection() -> dict[str, str]:
    """查看 GA4 OAuth 状态；未配置/未授权时返回可执行的下一步，不触发浏览器。"""

    return await _ga4.connection_status()


@mcp.tool(annotations=EXTERNAL_AUTHORIZATION_ACTION, title="连接 GA4")
@observe_tool(tool="connect_analytics")
@map_seo_data_errors
async def connect_analytics() -> dict[str, Any]:
    """显式发起 Google Analytics 4 Desktop OAuth。

    该 Tool 的外部交互由 Agent Host 原生 Tool Approval 控制；Plugin 不重复发起 approval elicitation。
    """

    return await _ga4.authorize()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="GA4 媒体资源列表")
@observe_tool(tool="list_analytics_properties")
@map_seo_data_errors
async def list_analytics_properties(domain: str | None = None) -> dict[str, Any]:
    """列出当前账号可访问的 GA4 Properties，并可按 Web Data Stream 域名匹配。

    传入 `domain` 时使用 Web Data Stream `defaultUri` 解析站点归属；Property 名称本身
    不作为域名绑定证据。该 Tool 用于显式列出/排障；分析 Tool 的最终 Property 由 hidden
    dependency 自动解析或通过 native elicitation 获取用户选择，不依赖列表顺序。
    """

    properties = await _ga4.list_properties()
    if not domain:
        return {"status": "complete", "properties": properties}

    matched_properties = await match_ga4_properties_for_domain(_ga4, domain)
    match_status = (
        "matched"
        if len(matched_properties) == 1
        else "ambiguous"
        if len(matched_properties) > 1
        else "not_found"
    )
    return {
        "status": "complete",
        "domain": domain,
        "match_status": match_status,
        "matched_properties": matched_properties,
        "properties": properties,
    }


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="自然流量与转化")
@observe_tool(
    tool="analyze_organic_traffic",
    capability="WebAnalytics",
    target_arg="target",
)
@map_seo_data_errors
async def analyze_organic_traffic(
    target: str,
    start_date: str,
    end_date: str,
    scope: Annotated[Ga4ResolvedScope, Resolve(_resolve_ga4_scope)],
    view: str = "overview",
    compare_start_date: str | None = None,
    compare_end_date: str | None = None,
    country_codes: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """分析 GA4 中 Organic Search 访客的站内行为与转化。

    `view` 支持 overview / landing_pages / countries / country_pages / devices / daily。
    `target` 接受站点域名或明确的 GA4 Property ID。Property 身份由 MCP dependency resolver 在
    Tool 执行前解析；唯一匹配自动继续，多候选通过 elicitation 让用户选择，模型不能直接填写隐藏 Property。
    这里只回答进站后的 sessions、engagement、key events、页面浏览和 revenue 等第一方事实；
    不把 GA4 当作关键词排名、Search Console 展示/点击或 Google 索引状态。
    """

    return (
        await _web_analytics.analyze(
            property_id=scope.property_id,
            start_date=start_date,
            end_date=end_date,
            view=view,
            compare_start_date=compare_start_date,
            compare_end_date=compare_end_date,
            country_codes=country_codes,
            site_domain=scope.site_domain,
            limit=limit,
            offset=offset,
        )
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="Google 搜索表现")
@observe_tool(
    tool="analyze_search_console",
    capability="SearchPerformance",
    target_arg="target",
)
@map_seo_data_errors
async def analyze_search_console(
    target: str,
    start_date: str,
    end_date: str,
    scope: Annotated[GscResolvedScope, Resolve(_resolve_gsc_scope)],
    dimensions: list[str] | None = None,
    query: str | None = None,
    page: str | None = None,
    country: str | None = None,
    device: str | None = None,
    data_state: str = "final",
    search_type: str = "web",
    row_limit: int = 1000,
    start_row: int = 0,
) -> dict[str, Any]:
    """读取站点的 Google 自然搜索第一方表现。

    `target` 接受 domain、URL 或明确的 `sc-domain:` Property。Property 身份由 MCP dependency resolver
    在 Tool 执行前解析；唯一匹配自动继续，多候选通过 elicitation 让用户选择。
    Query × Page 通过 `dimensions=["query", "page"]` 表达；空 rows 不能被解释成“未排名”。
    省略 dimensions 或传 null 使用默认 Query × Page；明确传 [] 则查询当前范围的不分组汇总。
    数据来源是 Google Search Console。第三方排名/可见性证据走独立数据能力，不能填入本结果。
    """

    result = await _search_performance.query(
        property_url=scope.property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=tuple(["query", "page"] if dimensions is None else dimensions),
        query=query,
        page=page,
        country=country,
        device=device,
        data_state=data_state,
        search_type=search_type,
        row_limit=row_limit,
        start_row=start_row,
    )
    return result.to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="自然排名与可见性")
@observe_tool(
    tool="analyze_rankings",
    capability="OrganicVisibility",
    target_arg="target",
)
@map_seo_data_errors
async def analyze_rankings(
    target: str,
    country: str,
    language: str,
    search_engine: str,
    view: str = "keywords",
    target_scope: str = "domain",
    limit: int = 100,
    offset: int = 0,
    historical_serp_mode: str = "live",
    date_from: str | None = None,
    date_to: str | None = None,
    include_snapshots: bool = False,
    snapshot_weeks: int = 8,
) -> dict[str, Any]:
    """读取任意公开 domain/URL 的第三方自然搜索可见性数据。

    当前 Provider 是 DataForSEO Labs。返回关键词排名、ranking URL、页面级可见性、
    overview 或历史趋势；estimated traffic 始终是第三方估算，不等于 GSC clicks。
    `view` 支持 overview/keywords/pages/history。`country/language/search_engine` 是 Product market，
    当前 DataForSEO Labs 实现只支持其 registry 中可用的 Google market；Provider code 由 Resolver 解析。
    成功查询会自动保存本地周聚合快照；`include_snapshots=true` 时返回最近实际观测周，
    缺失周不会自动补值，可用于“最近一周/最近 8 周”这类趋势报表。
    最终用户结果应描述 SEO 含义和 DataForSEO 来源，不应展示 Gateway/Adapter/Client 等内部实现名。
    """

    return (
        await _organic_visibility.inspect(
            target,
            country=country,
            language=language,
            search_engine=search_engine,
            view=view,
            target_scope=target_scope,
            limit=limit,
            offset=offset,
            historical_serp_mode=historical_serp_mode,
            date_from=date_from,
            date_to=date_to,
            include_snapshots=include_snapshots,
            snapshot_weeks=snapshot_weeks,
        )
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="关键词研究")
@observe_tool(
    tool="research_keywords",
    capability="KeywordResearch",
    target_arg="keyword",
)
@map_seo_data_errors
async def research_keywords(
    keyword: str,
    country: str,
    language: str,
    search_engine: str,
    month: str | None = None,
    include_related: bool = False,
    include_questions: bool = False,
    idea_limit: int | None = None,
) -> dict[str, Any]:
    """读取 Semrush `KeywordResearch`。

    返回搜索量、SEO Keyword Difficulty、Intent、CPC、PPC Competitive Density、趋势和
    SERP features。Related/Questions 只有显式请求才调用；用户未说明数量时默认最多返回 20 个词，避免无意义消耗 API units。
    `country/language/search_engine` 必须显式传入；当前 Semrush 路径是 Google evidence，regional database
    由 Resolver 从已验证 coverage 生成，不接受上层猜 database。v4 不可用时可使用现有 v3 Key fallback；
    Semrush 研究数据不替代 GSC 本站排名事实。
    """

    return (
        await _keyword_research.research(
            keyword,
            country=country,
            language=language,
            search_engine=search_engine,
            month=month,
            include_related=include_related,
            include_questions=include_questions,
            idea_limit=idea_limit,
        )
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="竞品 SEO 研究")
@observe_tool(
    tool="research_competitors",
    capability="CompetitorResearch",
    target_arg="domain",
)
@map_seo_data_errors
async def research_competitors(
    domain: str,
    country: str,
    language: str,
    search_engine: str,
    compare_domains: list[str] | None = None,
    limit: int = 10,
    keyword_limit: int | None = None,
) -> dict[str, Any]:
    """读取 Semrush `CompetitorResearch`。

    默认组合 Domain Overview、Organic Competitors、Organic Pages；只有明确传入
    `compare_domains` 时才调用昂贵的 Keyword Gap。Gap 关键词在用户未说明数量时默认最多 20 个；
    竞争域名和页面列表仍由 `limit` 单独控制。`country/language/search_engine` 是 Product market；当前
    Semrush Domain Analytics 路径只作为 Google evidence，regional database 由 Resolver 解析。这里不创建
    Semrush Project，也不使用 Position Tracking / Site Audit。
    """

    return (
        await _competitor_research.research(
            domain,
            country=country,
            language=language,
            search_engine=search_engine,
            compare_domains=compare_domains,
            limit=limit,
            keyword_limit=keyword_limit,
        )
    ).to_dict()


@mcp.tool(annotations=READ_ONLY_OPEN_WORLD, title="搜索结果研究")
@observe_tool(tool="research_serp", capability="SerpResearch", target_arg="query")
@map_seo_data_errors
async def research_serp(
    query: str,
    country: str,
    language: str,
    search_engine: str,
    num: int = 10,
    location: str | None = None,
) -> dict[str, Any]:
    """读取实时 `SerpResearch`。

    返回当前自然结果、PAA、SERP features 和轻量 Knowledge Graph；当前 Provider 是 Serper/Google，
    因此非 Google `search_engine` 会返回 capability unsupported，而不会把 Google 结果伪装成百度。
    这些是搜索结果页事实，
    不能替代 GSC SearchPerformance，也不能替代 PageInspection 的页面源 HTML。
    """

    return (
        await _serp_research.research(
            query,
            country=country,
            language=language,
            search_engine=search_engine,
            num=num,
            location=location,
        )
    ).to_dict()


def main() -> None:
    """以 stdio 启动 MCP 数据服务；模型推理仍由 Codex/其他 Host 负责。"""

    # MCP Python SDK v2 的 run() 默认就是 stdio，适合 Codex/Agent Plugin 本地启动。
    mcp.run()


if __name__ == "__main__":
    main()
