from __future__ import annotations

from collections.abc import Iterable

from codex_seo_mcp.adapters.base import CapabilityAdapter


class CapabilityRegistry:
    """Bind implemented capability names to already-constructed adapters.

    Registry deliberately does not construct clients or adapters. Runtime composition belongs to
    the composition root so capability binding cannot silently create a second dependency graph.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, CapabilityAdapter] = {}

    def register(self, capability: str, adapter: CapabilityAdapter) -> None:
        if capability in self._adapters:
            raise ValueError(f"Capability 已重复注册：{capability}")
        self._adapters[capability] = adapter

    def get(self, capability: str) -> CapabilityAdapter:
        try:
            return self._adapters[capability]
        except KeyError as exc:
            raise KeyError(f"Capability 尚未实现：{capability}") from exc

    def capabilities(self) -> list[str]:
        return sorted(self._adapters)


def build_registry(adapters: Iterable[CapabilityAdapter]) -> CapabilityRegistry:
    """Bind the supplied adapters without owning their construction lifecycle."""

    registry = CapabilityRegistry()
    for adapter in adapters:
        registry.register(adapter.capability, adapter)
    return registry
