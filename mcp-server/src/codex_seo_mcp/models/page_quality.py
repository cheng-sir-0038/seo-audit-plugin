from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PageQualityMetric:
    """单个 Lighthouse Lab 指标。

    业务说明：`numeric_value` 保留 Lighthouse 原始数值尺度，`unit` 明确单位，避免上层
    把 LCP 毫秒、CLS 无量纲等数据混在一起比较。`score` 只是本次 Lab Audit 的评分，
    不能直接解释成 Google 的自然搜索排名分数。
    """

    numeric_value: float | None
    unit: str
    display_value: str | None
    score: int | None


@dataclass(slots=True)
class PageQualityIssue:
    """Lighthouse 提示的机会项或诊断项。

    这些条目是页面质量线索，不等于最终 SEO Finding；是否值得修改仍需结合页面用途、
    仓库实现和其他数据由 Product Skill 判断。
    """

    audit_id: str
    title: str
    description: str | None
    score: int | None
    display_value: str | None
    estimated_savings_ms: int | None = None
    estimated_savings_bytes: int | None = None
    business_label: str | None = None
    recommendations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PageQualityLab:
    """PageSpeed/Lighthouse 的实验室测量结果。"""

    requested_url: str
    final_url: str
    lighthouse_version: str | None
    fetch_time: str | None
    category_scores: dict[str, int | None]
    metrics: dict[str, PageQualityMetric]
    opportunities: list[PageQualityIssue] = field(default_factory=list)
    diagnostics: list[PageQualityIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PageQualityFieldBucket:
    """CrUX histogram 的一个真实用户体验区间。"""

    start: float | None
    end: float | None
    density: float


@dataclass(slots=True)
class PageQualityFieldMetric:
    """单个 CrUX Field 指标。

    `p75` 是 CrUX 官方提供的 75 分位值；histogram 则保留真实用户体验在各区间的
    分布，避免上层只看到一个数字后丢失样本结构。
    """

    p75: float | None
    unit: str
    histogram: list[PageQualityFieldBucket] = field(default_factory=list)


@dataclass(slots=True)
class PageQualityField:
    """CrUX 聚合的真实 Chrome 用户体验数据。

    `scope=url` 表示当前 URL 自身有足够样本；`scope=origin` 表示 URL 样本不足后回退
    到站点 Origin。两者不能混为一谈，否则会把站点级体验误写成单页事实。
    """

    scope: str
    key: str
    form_factor: str
    collection_start: str | None
    collection_end: str | None
    metrics: dict[str, PageQualityFieldMetric] = field(default_factory=dict)


@dataclass(slots=True)
class PageQuality:
    """页面质量的统一领域结果。

    对外只有一个 `PageQuality` 能力，但 `lab` 与 `field` 必须保持来源独立。两者都可用时
    CapabilityResult 为 complete；任一侧缺失时保留另一侧并返回 partial。
    """

    url: str
    strategy: str
    lab: PageQualityLab | None
    field: PageQualityField | None
