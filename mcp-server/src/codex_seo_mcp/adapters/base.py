from __future__ import annotations

from typing import Protocol


class CapabilityAdapter(Protocol):
    """领域能力 Adapter 的最小公共契约。

    Adapter 是 Provider 与 Product Skill 之间的稳定边界：Provider 可以换版本、换厂商，
    但上层只依赖 `capability` 和领域结果，不应该理解第三方原始字段或错误码。
    """

    capability: str
