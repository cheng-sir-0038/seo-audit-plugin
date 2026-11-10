from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class Confidence(StrEnum):
    """诊断结论的可靠程度，不代表业务影响大小。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CapabilityStatus(StrEnum):
    """一次成功能力调用的数据完整度。Provider 不可用不属于 Result 状态。"""

    COMPLETE = "complete"
    PARTIAL = "partial"


class CapabilitySourceKind(StrEnum):
    """能力事实的来源性质。"""

    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    RUNTIME = "runtime"
    MEASUREMENT = "measurement"


@dataclass(slots=True)
class CapabilityResult(Generic[T]):
    """统一能力返回外壳。

    业务说明：`status` 描述“这次数据采集是否完整”，不描述 SEO 好坏。
    页面真的存在 noindex、缺 Title 等问题时，采集仍然可以是 complete；这些问题
    应该出现在 data/warnings 里交给诊断层判断，不能混成“数据获取失败”。
    """

    capability: str
    provider: str
    source_kind: CapabilitySourceKind
    status: CapabilityStatus
    data: T
    warnings: list[str]
    fetched_at: str

    @classmethod
    def partial(
        cls,
        *,
        capability: str,
        provider: str,
        source_kind: CapabilitySourceKind | str,
        data: T,
        warnings: list[str] | None = None,
    ) -> "CapabilityResult[T]":
        """返回可用但不完整的数据结果。

        业务说明：例如 PageQuality 已有 Lighthouse Lab、尚无 CrUX Field 时就是 partial。
        这不代表页面质量差，只表示当前能力的数据面还没有完整覆盖。
        """

        return cls(
            capability=capability,
            provider=provider,
            source_kind=_source_kind(source_kind),
            status=CapabilityStatus.PARTIAL,
            data=data,
            warnings=list(warnings or []),
            fetched_at=datetime.now(UTC).isoformat(),
        )

    @classmethod
    def complete(
        cls,
        *,
        capability: str,
        provider: str,
        source_kind: CapabilitySourceKind | str,
        data: T,
        warnings: list[str] | None = None,
    ) -> "CapabilityResult[T]":
        """返回数据面完整的能力结果。

        `complete` 只说明本次需要的数据已经拿齐，不表示 SEO 状态正常；例如页面明确
        返回 noindex 时，PageInspection 仍然可以是 complete。
        """

        return cls(
            capability=capability,
            provider=provider,
            source_kind=_source_kind(source_kind),
            status=CapabilityStatus.COMPLETE,
            data=data,
            warnings=list(warnings or []),
            fetched_at=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_kind"] = self.source_kind.value
        payload["status"] = self.status.value
        return payload


def _source_kind(value: CapabilitySourceKind | str) -> CapabilitySourceKind:
    return value if isinstance(value, CapabilitySourceKind) else CapabilitySourceKind(str(value))
