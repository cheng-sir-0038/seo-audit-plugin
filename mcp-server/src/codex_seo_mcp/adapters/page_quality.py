from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Protocol
from urllib.parse import urlparse

from codex_seo_mcp.clients.crux import CruxClient, CruxResponse
from codex_seo_mcp.clients.pagespeed import PageSpeedClient, PageSpeedResponse, validate_pagespeed_response
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.page_quality_url import normalize_page_quality_url
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.page_quality import (
    PageQuality,
    PageQualityField,
    PageQualityFieldBucket,
    PageQualityFieldMetric,
    PageQualityIssue,
    PageQualityLab,
    PageQualityMetric,
)

_CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
_METRICS = {
    "fcp": ("first-contentful-paint", "ms"),
    "lcp": ("largest-contentful-paint", "ms"),
    "cls": ("cumulative-layout-shift", "unitless"),
    "tbt": ("total-blocking-time", "ms"),
    "speed_index": ("speed-index", "ms"),
}
_EXCLUDED_DISPLAY_MODES = {"manual", "notApplicable", "informative"}
_ISSUE_GUIDANCE: dict[str, tuple[str, tuple[str, ...]]] = {
    "unused-javascript": (
        "未使用的 JavaScript 过多",
        (
            "删除当前页面不需要的 JavaScript，避免把整站代码一次性下发到首屏。",
            "按页面或功能拆分代码，非首屏功能等真正需要时再加载。",
            "审查第三方脚本，只保留必要脚本并尽量延后加载。",
        ),
    ),
    "bootup-time": (
        "JavaScript 执行占用主线程过久",
        (
            "减少首屏必须执行的 JavaScript 体积和初始化逻辑。",
            "把长任务拆成更小的任务，让浏览器有机会及时响应用户操作。",
            "把非关键计算延后到首屏渲染或用户交互之后。",
        ),
    ),
    "mainthread-work-breakdown": (
        "浏览器主线程工作过重",
        (
            "优先减少 JavaScript 解析、编译和执行时间。",
            "拆分长任务并降低一次性 DOM / 样式计算的规模。",
            "把可以异步或延后的工作移出首屏关键路径。",
        ),
    ),
    "render-blocking-resources": (
        "首屏渲染被 CSS 或 JavaScript 阻塞",
        (
            "只保留首屏必须的关键 CSS，其他样式延后加载。",
            "对非关键 JavaScript 使用 defer/async 或延迟到首屏之后执行。",
            "减少首屏关键路径中的同步资源数量和依赖链。",
        ),
    ),
    "uses-responsive-images": (
        "图片尺寸大于实际展示需要",
        (
            "使用 srcset/sizes 或图片 CDN，按设备和实际展示尺寸下发图片。",
            "避免移动端下载桌面端超大图片。",
            "为常用展示尺寸预生成合适分辨率的图片版本。",
        ),
    ),
    "uses-optimized-images": (
        "图片体积可以进一步压缩",
        (
            "在可接受画质下提高图片压缩率。",
            "优先使用 WebP / AVIF 等更高效的图片格式。",
            "通过图片 CDN 自动做格式转换、压缩和尺寸裁剪。",
        ),
    ),
    "modern-image-formats": (
        "图片格式不够高效",
        (
            "优先把 JPEG/PNG 等大图转换为 WebP 或 AVIF。",
            "保留兼容回退，但让支持现代格式的浏览器优先下载更小资源。",
        ),
    ),
    "offscreen-images": (
        "非首屏图片过早加载",
        (
            "对首屏之外的图片使用懒加载，减少页面打开时的网络竞争。",
            "首屏主图或 LCP 图片不要懒加载，避免反过来拖慢主要内容。",
        ),
    ),
    "lcp-lazy-loaded": (
        "主要内容图片被延迟加载",
        (
            "不要给 LCP 主图使用 lazy loading。",
            "让主图在初始 HTML 中尽早可发现，必要时使用 preload。",
            "对明确的首屏主要图片设置较高加载优先级，例如 fetchpriority=high。",
        ),
    ),
    "server-response-time": (
        "服务器开始响应页面的速度偏慢",
        (
            "检查后端处理、数据库查询和模板渲染耗时，缩短首个 HTML 响应时间。",
            "对可缓存页面使用 CDN / 页面缓存，减少每次都回源计算。",
            "减少入口重定向和不必要的上游网络请求。",
        ),
    ),
    "redirects": (
        "页面加载前存在额外重定向",
        (
            "让站内链接和入口地址直接指向最终 URL。",
            "合并或删除不必要的多级跳转，避免每次跳转都增加网络等待。",
        ),
    ),
    "uses-long-cache-ttl": (
        "静态资源浏览器缓存时间偏短",
        (
            "对带版本号或内容哈希的静态资源设置长期 Cache-Control。",
            "使用 CDN 缓存图片、CSS、JavaScript 和字体，减少重复下载。",
        ),
    ),
    "font-display": (
        "字体加载可能延迟文字显示",
        (
            "为自定义字体配置 font-display: swap 或 optional。",
            "只预加载首屏真正需要的字体，并减少不必要的字重和字体文件。",
            "对大型字体做子集化，减少首次下载体积。",
        ),
    ),
    "dom-size": (
        "页面 DOM 规模过大",
        (
            "删除无用的嵌套节点和重复结构，降低页面 DOM 复杂度。",
            "长列表或复杂模块按需渲染，必要时使用虚拟列表。",
            "避免一次交互触发大范围 DOM 和样式重算。",
        ),
    ),
    "layout-shifts": (
        "页面加载过程中存在布局跳动",
        (
            "为图片、广告、iframe 等异步内容预留明确宽高或占位空间。",
            "避免在已展示内容上方动态插入新元素。",
            "稳定字体加载，减少字体切换造成的文字尺寸变化。",
        ),
    ),
    "third-party-summary": (
        "第三方脚本带来较高性能开销",
        (
            "删除低价值第三方脚本，优先保留对业务真正必要的服务。",
            "把统计、客服、广告等非首屏脚本延后加载。",
            "评估能否使用更轻量实现或减少第三方脚本执行频率。",
        ),
    ),
}
_CRUX_METRICS = {
    "lcp": ("largest_contentful_paint", "ms"),
    "inp": ("interaction_to_next_paint", "ms"),
    "cls": ("cumulative_layout_shift", "unitless"),
    "fcp": ("first_contentful_paint", "ms"),
    "ttfb": ("experimental_time_to_first_byte", "ms"),
}


class PageSpeedLike(Protocol):
    """PageQuality 对 PageSpeed Client 的最小依赖面，测试和后续替换都走这个 seam。"""

    async def analyze(
        self,
        url: str,
        *,
        strategy: str,
        categories: tuple[str, ...],
        locale: str,
    ) -> PageSpeedResponse: ...


class CruxLike(Protocol):
    """PageQuality 对 CrUX Client 的最小依赖面。"""

    async def query_url(
        self, url: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None: ...

    async def query_origin(
        self, origin: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None: ...


class PageQualityAdapter:
    """把 PageSpeed/Lighthouse 原始响应转换为 `PageQuality` 领域结果。

    业务边界：Lab 只来自 PageSpeed/Lighthouse，Field 只来自 CrUX。Google 已建议真实
    用户体验直接使用 CrUX API，因此这里不读取 PSI 响应里的 loadingExperience 来
    假装 Field 数据。两个 Provider 彼此隔离，一边失败不能抹掉另一边已经拿到的数据。
    """

    capability = "PageQuality"

    def __init__(
        self,
        pagespeed: PageSpeedLike | None = None,
        crux: CruxLike | None = None,
    ) -> None:
        self.pagespeed = pagespeed or PageSpeedClient()
        self.crux = crux or CruxClient()

    async def inspect(
        self,
        url: str,
        *,
        strategy: str,
        locale: str = "zh-CN",
    ) -> CapabilityResult[PageQuality]:
        selected_strategy = strategy.strip().lower()
        if selected_strategy not in {"mobile", "desktop"}:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "页面性能检测只支持 mobile 或 desktop")
        target = normalize_page_quality_url(url)

        warnings: list[str] = []
        lab: PageQualityLab | None = None
        field: PageQualityField | None = None
        lab_error: SeoDataError | None = None
        field_error: SeoDataError | None = None

        try:
            response = await self.pagespeed.analyze(
                target,
                strategy=selected_strategy,
                categories=_CATEGORIES,
                locale=locale or "zh-CN",
            )
            lab = _map_lighthouse(response.payload)
            warnings.extend(lab.warnings)
        except SeoDataError as exc:
            lab_error = exc
            warnings.append(f"Google PageSpeed Insights 实验室检测不可用：{exc.code}")

        try:
            field, field_warnings = await self._load_field(target, selected_strategy)
            warnings.extend(field_warnings)
        except SeoDataError as exc:
            field_error = exc
            warnings.append(f"CrUX 真实用户体验数据不可用：{exc.code}")

        if lab is None and field is None:
            # 两边都没有可用数据时，保留最能解释当前失败的 Provider 错误；不能返回一份
            # data=None 的假成功结果。
            raise lab_error or field_error or SeoDataError(SeoDataErrorCode.DATA_UNAVAILABLE, "页面性能与体验当前没有可用检测数据"
            )

        resolved_url = (
            (lab.final_url or lab.requested_url) if lab else target
        ) or target
        data = PageQuality(
            url=resolved_url,
            strategy=selected_strategy,
            lab=lab,
            field=field,
        )

        providers = "+".join(
            name for name, present in (("pagespeed", lab is not None), ("crux", field is not None)) if present
        )
        factory = CapabilityResult.complete if lab is not None and field is not None else CapabilityResult.partial
        return factory(
            capability=self.capability,
            provider=providers,
            source_kind=CapabilitySourceKind.MEASUREMENT,
            data=data,
            warnings=warnings,
        )

    async def _load_field(
        self, url: str, strategy: str
    ) -> tuple[PageQualityField | None, list[str]]:
        form_factor = "PHONE" if strategy == "mobile" else "DESKTOP"
        metric_names = tuple(provider_name for provider_name, _unit in _CRUX_METRICS.values())
        url_response = await self.crux.query_url(
            url, form_factor=form_factor, metrics=metric_names
        )
        if url_response is not None:
            return _map_crux(
                url_response.payload, expected_scope="url", expected_key=url, form_factor=form_factor,
            ), []

        origin = _origin(url)
        origin_response = await self.crux.query_origin(
            origin, form_factor=form_factor, metrics=metric_names
        )
        if origin_response is not None:
            return _map_crux(
                origin_response.payload, expected_scope="origin", expected_key=origin, form_factor=form_factor,
            ), [
                "CrUX URL 级真实用户样本不足，已回退到站点 Origin 数据"
            ]
        return None, ["CrUX 当前 URL/Origin 没有足够真实用户样本"]


def _map_lighthouse(payload: Mapping[str, object]) -> PageQualityLab:
    validate_pagespeed_response(payload)
    lighthouse = _mapping(payload.get("lighthouseResult"))

    categories = _mapping(lighthouse.get("categories"))
    audits = _mapping(lighthouse.get("audits"))
    category_scores = {
        category: _score_100(_mapping(categories.get(category)).get("score"))
        for category in _CATEGORIES
    }
    metrics = {
        name: _metric(audits, audit_id, unit)
        for name, (audit_id, unit) in _METRICS.items()
    }
    opportunities, diagnostics = _issues(audits)

    if not (
        any(score is not None for score in category_scores.values())
        or any(metric.numeric_value is not None or metric.score is not None for metric in metrics.values())
        or opportunities or diagnostics
    ):
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed 响应没有可用的实验室测量")

    # runWarnings 是本次 Lighthouse 执行环境的警告，应保留给调用方判断数据可靠性。
    warnings = [str(item) for item in lighthouse.get("runWarnings") or [] if str(item).strip()]
    return PageQualityLab(
        requested_url=_text(lighthouse.get("requestedUrl")) or "",
        final_url=_text(lighthouse.get("finalUrl")) or "",
        lighthouse_version=_text(lighthouse.get("lighthouseVersion")),
        fetch_time=_text(lighthouse.get("fetchTime")),
        category_scores=category_scores,
        metrics=metrics,
        opportunities=opportunities,
        diagnostics=diagnostics,
        warnings=warnings,
    )


def _map_crux(
    payload: Mapping[str, object], *, expected_scope: str, expected_key: str, form_factor: str,
) -> PageQualityField:
    """把 CrUX record 映射为稳定 Field 领域模型，保留 URL/Origin scope。"""

    record = _mapping(payload.get("record"))
    if not record:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX 响应缺少 record")
    key = _mapping(record.get("key"))
    if set(key).intersection({"url", "origin"}) != {expected_scope}:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX record.key 范围与请求不一致")
    if key.get("formFactor") != form_factor:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX record.key 设备与请求不一致")
    scope = expected_scope
    key_value = key.get(scope)
    if not isinstance(key_value, str) or not key_value:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX record.key 目标缺失或格式无效")
    if key_value != expected_key:
        # 只有供应商明确关联了请求地址与规范化地址，才能接受不同的结果 key。
        normalization = _mapping(payload.get("urlNormalizationDetails"))
        if normalization.get("originalUrl") != expected_key or normalization.get("normalizedUrl") != key_value:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX record.key 目标与请求不一致")

    raw_metrics = _mapping(record.get("metrics"))
    metrics: dict[str, PageQualityFieldMetric] = {}
    for domain_name, (provider_name, unit) in _CRUX_METRICS.items():
        raw_metric = _mapping(raw_metrics.get(provider_name))
        if not raw_metric:
            continue
        percentiles = _mapping(raw_metric.get("percentiles"))
        histogram: list[PageQualityFieldBucket] = []
        for raw_bucket in raw_metric.get("histogram") or []:
            bucket = _mapping(raw_bucket)
            density = _number(bucket.get("density"))
            if density is None:
                continue
            if not 0 <= density <= 1:
                raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX 分布占比超出 0 到 1")
            histogram.append(
                PageQualityFieldBucket(
                    start=_number(bucket.get("start")),
                    end=_number(bucket.get("end")),
                    density=density,
                )
            )
        metrics[domain_name] = PageQualityFieldMetric(
            p75=_number(percentiles.get("p75")),
            unit=unit,
            histogram=histogram,
        )

    if not any(metric.p75 is not None or metric.histogram for metric in metrics.values()):
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX 响应没有可用的真实用户测量")

    period = _mapping(record.get("collectionPeriod"))
    return PageQualityField(
        scope=scope,
        key=key_value,
        form_factor=form_factor,
        collection_start=_date_text(_mapping(period.get("firstDate"))),
        collection_end=_date_text(_mapping(period.get("lastDate"))),
        metrics=metrics,
    )


def _origin(url: str) -> str:
    """CrUX URL 级无样本时，生成同协议/主机/端口的 Origin fallback。"""

    parsed = urlparse(normalize_page_quality_url(url))
    return f"{parsed.scheme}://{parsed.netloc}"


def _date_text(value: Mapping[str, object]) -> str | None:
    year = _int_number(value.get("year"))
    month = _int_number(value.get("month"))
    day = _int_number(value.get("day"))
    if year is None or month is None or day is None:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _metric(
    audits: Mapping[str, object], audit_id: str, unit: str
) -> PageQualityMetric:
    audit = _mapping(audits.get(audit_id))
    return PageQualityMetric(
        numeric_value=_number(audit.get("numericValue")),
        unit=unit,
        display_value=_text(audit.get("displayValue")),
        score=_score_100(audit.get("score")),
    )


def _issues(
    audits: Mapping[str, object],
) -> tuple[list[PageQualityIssue], list[PageQualityIssue]]:
    opportunities: list[PageQualityIssue] = []
    diagnostics: list[PageQualityIssue] = []
    metric_audit_ids = {audit_id for audit_id, _unit in _METRICS.values()}

    for raw_audit_id, raw_value in audits.items():
        audit_id = str(raw_audit_id)
        if audit_id in metric_audit_ids:
            continue
        audit = _mapping(raw_value)
        if _text(audit.get("scoreDisplayMode")) in _EXCLUDED_DISPLAY_MODES:
            continue

        score = _score_100(audit.get("score"))
        details = _mapping(audit.get("details"))
        savings_ms = _savings(details, "overallSavingsMs", "wastedMs")
        savings_bytes = _savings(details, "overallSavingsBytes", "wastedBytes")
        if savings_ms is None and savings_bytes is None and (score is None or score >= 90):
            continue

        business_label, recommendations = _issue_guidance(audit_id)
        issue = PageQualityIssue(
            audit_id=audit_id,
            title=_text(audit.get("title")) or audit_id,
            description=_text(audit.get("description")),
            score=score,
            display_value=_text(audit.get("displayValue")),
            estimated_savings_ms=savings_ms,
            estimated_savings_bytes=savings_bytes,
            business_label=business_label,
            recommendations=list(recommendations),
        )
        # 有明确节省量的是“机会项”；其余低分 Audit 作为诊断项，避免把所有 Audit 混成一张表。
        if savings_ms is not None or savings_bytes is not None:
            opportunities.append(issue)
        else:
            diagnostics.append(issue)

    opportunities.sort(key=_issue_order)
    diagnostics.sort(key=_issue_order)
    return opportunities, diagnostics


def _issue_order(issue: PageQualityIssue) -> tuple[int, int, int, str]:
    return (
        -(issue.estimated_savings_ms or 0),
        -(issue.estimated_savings_bytes or 0),
        issue.score if issue.score is not None else 101,
        issue.audit_id,
    )


def _issue_guidance(audit_id: str) -> tuple[str | None, tuple[str, ...]]:
    return _ISSUE_GUIDANCE.get(audit_id, (None, ()))


def _savings(details: Mapping[str, object], overall_key: str, item_key: str) -> int | None:
    direct = _number(details.get(overall_key))
    if direct is not None and direct > 0:
        return int(round(direct))
    total = 0.0
    found = False
    for raw_item in details.get("items") or []:
        item = _mapping(raw_item)
        value = _number(item.get(item_key))
        if value is not None and value > 0:
            total += value
            if not isfinite(total):
                raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed 预计节省量计算溢出")
            found = True
    return int(round(total)) if found else None


def _score_100(value: object) -> int | None:
    numeric = _number(value)
    if numeric is None:
        return None
    if not 0 <= numeric <= 1:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed 原始评分超出 0 到 1")
    return int(round(numeric * 100))


def _number(value: object) -> float | None:
    if value is None:
        return None
    # 缺失仍是未知；已返回的异常值不能变成正常分数，也不能破坏另一来源的结果。
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            number = float(value)
        except (ValueError, OverflowError):
            pass
        else:
            if isfinite(number):
                return number
    raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "页面性能指标不是有限数值")


def _int_number(value: object) -> int | None:
    numeric = _number(value)
    return int(numeric) if numeric is not None else None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
