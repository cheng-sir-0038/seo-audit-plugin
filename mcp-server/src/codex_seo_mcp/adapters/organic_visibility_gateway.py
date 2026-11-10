from __future__ import annotations

from typing import Protocol

from codex_seo_mcp.adapters.organic_visibility import (
    DataForSEOOrganicVisibilityAdapter,
    OrganicVisibilityProviderDescriptor,
)
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.models.organic_visibility import OrganicVisibility


class OrganicVisibilityProvider(Protocol):
    capability: str
    provider: str

    @property
    def descriptor(self) -> OrganicVisibilityProviderDescriptor: ...

    async def inspect(
        self,
        target: str,
        *,
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
    ) -> CapabilityResult[OrganicVisibility]: ...


_FALLBACK_ERRORS = {
    SeoDataErrorCode.NOT_CONFIGURED,
    SeoDataErrorCode.AUTHORIZATION_REQUIRED,
    SeoDataErrorCode.PERMISSION_DENIED,
    SeoDataErrorCode.QUOTA_EXCEEDED,
    SeoDataErrorCode.RATE_LIMITED,
    SeoDataErrorCode.PROVIDER_UNAVAILABLE,
    SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
}


class OrganicVisibilityGateway:
    """Route OrganicVisibility requests through ordered Provider fallback.

    The gateway never fans out all providers and never merges provider positions. It returns one
    provider result per request. Cross-provider corroboration remains a diagnosis-layer operation.
    """

    capability = "OrganicVisibility"

    def __init__(
        self,
        providers: list[OrganicVisibilityProvider] | None = None,
    ) -> None:
        self.providers: list[OrganicVisibilityProvider] = list(
            providers or [DataForSEOOrganicVisibilityAdapter()]
        )
        if not self.providers:
            raise ValueError("OrganicVisibilityGateway 至少需要一个 Provider Adapter")

    async def inspect(
        self,
        target: str,
        *,
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
    ) -> CapabilityResult[OrganicVisibility]:
        selected_view = view.strip().lower()
        selected_scope = target_scope.strip().lower()
        candidates = [
            provider
            for provider in self.providers
            if (selected_view, selected_scope) in provider.descriptor.supported_view_scopes
        ]
        if not candidates:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST,
                f"没有 OrganicVisibility Provider 支持 view={selected_view}, scope={selected_scope}",
            )

        failures: list[tuple[str, SeoDataError]] = []
        for provider in candidates:
            try:
                result = await provider.inspect(
                    target,
                    country=country,
                    language=language,
                    search_engine=search_engine,
                    view=selected_view,
                    target_scope=selected_scope,
                    limit=limit,
                    offset=offset,
                    historical_serp_mode=historical_serp_mode,
                    date_from=date_from,
                    date_to=date_to,
                )
            except SeoDataError as exc:
                if exc.code not in _FALLBACK_ERRORS:
                    raise
                failures.append((provider.provider, exc))
                continue

            if failures:
                fallback_note = "; ".join(
                    f"{provider_name}:{error.code}" for provider_name, error in failures
                )
                result.warnings.append(
                    f"OrganicVisibility fallback 已发生：{fallback_note}；当前使用 {result.provider}。"
                )
            return result

        if len(failures) == 1:
            raise failures[0][1]
        if failures and all(error.code is SeoDataErrorCode.NOT_CONFIGURED for _, error in failures):
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED,
                "OrganicVisibility 当前没有已配置的 Provider 凭据",
            )
        details = "; ".join(
            f"{provider_name}:{error.code}" for provider_name, error in failures
        )
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE,
            f"OrganicVisibility 当前没有可用 Provider{f'（{details}）' if details else ''}",
        )
