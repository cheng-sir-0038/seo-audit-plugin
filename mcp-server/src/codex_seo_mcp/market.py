from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


_COUNTRY_ALIASES = {
    "UK": "GB",
}

# Semrush's current Domain Analytics country list is the coverage authority for the v3 regional
# database resolver. Most provider database codes are the lower-case provider country code, but
# only AFTER membership in this verified coverage set; GB is normalized to Semrush's UK code.
# Mainland CN is intentionally absent from the current list and must not be guessed as `cn`.
_SEMRUSH_V3_PROVIDER_COUNTRIES = frozenset(
    {
        "AF", "AL", "DZ", "AO", "AR", "AM", "AU", "AT", "AZ", "BS", "BH", "BD",
        "BY", "BE", "BZ", "BO", "BA", "BW", "BR", "BN", "BG", "CV", "KH", "CM",
        "CA", "CL", "CO", "CG", "CR", "HR", "CY", "CZ", "DK", "DO", "EC", "EG",
        "SV", "EE", "ET", "FI", "FR", "GE", "DE", "GH", "GR", "GT", "GY", "HT",
        "HN", "HK", "HU", "IS", "IN", "ID", "IE", "IL", "IT", "JM", "JP", "JO",
        "KZ", "KW", "LV", "LB", "LY", "LT", "LU", "MG", "MY", "MT", "MU", "MX",
        "MD", "MN", "ME", "MA", "MZ", "NA", "NP", "NL", "NZ", "NI", "NG", "NO",
        "OM", "PK", "PY", "PE", "PH", "PL", "PT", "RO", "RU", "SA", "SN", "RS",
        "SG", "LK", "SK", "SI", "ZA", "KR", "ES", "SE", "TH", "TT", "TN", "TR",
        "UA", "AE", "UK", "US", "UY", "VE", "VN", "ZM", "ZW",
    }
)


@dataclass(frozen=True, slots=True)
class MarketContext:
    """Provider-neutral search market used by Product Skills and domain capabilities.

    Country is canonical ISO alpha-2, language is BCP47-like, and search_engine is a business
    semantic. Provider-specific location/database codes never belong here.
    """

    country: str
    language: str
    search_engine: str
    location: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        country: str,
        language: str,
        search_engine: str,
        location: str | None = None,
    ) -> "MarketContext":
        clean_country = _normalize_country(country)
        clean_language = _normalize_language(language)
        clean_engine = _normalize_search_engine(search_engine)
        clean_location = (location or "").strip() or None
        return cls(
            country=clean_country,
            language=clean_language,
            search_engine=clean_engine,
            location=clean_location,
        )


@dataclass(frozen=True, slots=True)
class ProviderMarket:
    """Provider wire market resolved from a stable MarketContext."""

    provider: str
    capability: str
    supported: bool
    search_engine: str
    provider_country: str | None = None
    location_code: int | None = None
    location_name: str | None = None
    language_code: str | None = None
    database: str | None = None
    resolution_source: str = "unknown"
    warnings: tuple[str, ...] = field(default_factory=tuple)


class DataForSEOLabsLocationClient(Protocol):
    async def locations_and_languages(self) -> list[dict[str, object]]: ...


class DataForSEOLabsMarketResolver:
    """Resolve DataForSEO Labs market only from its official capability registry."""

    def __init__(self, client: DataForSEOLabsLocationClient) -> None:
        self.client = client
        self._cache: dict[tuple[str, str, str, str], ProviderMarket] = {}

    async def resolve(
        self,
        market: MarketContext,
        *,
        capability: str,
        source: str = "google",
    ) -> ProviderMarket:
        selected_source = source.strip().lower()
        if market.search_engine != selected_source:
            raise SeoDataError(SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                (
                    f"当前 {capability} 的 DataForSEO Labs resolver 使用 {selected_source}，"
                    f"不能处理 search_engine={market.search_engine}"
                ),
            )

        key = (
            capability.strip().lower(),
            market.country,
            market.language.lower(),
            selected_source,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        locations = await self.client.locations_and_languages()
        candidates: list[tuple[dict[str, object], dict[str, object]]] = []
        for raw_location in locations:
            if str(raw_location.get("country_iso_code") or "").upper() != market.country:
                continue
            available_languages = raw_location.get("available_languages")
            if not isinstance(available_languages, list):
                continue
            for raw_language in available_languages:
                if not isinstance(raw_language, dict):
                    continue
                sources = {
                    str(item).strip().lower()
                    for item in (raw_language.get("available_sources") or [])
                    if str(item).strip()
                }
                if selected_source not in sources:
                    continue
                candidates.append((raw_location, raw_language))

        selected = _select_provider_language(candidates, market.language)
        if selected is None:
            raise SeoDataError(SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                (
                    f"当前 DataForSEO Labs 不支持 {capability} 的 "
                    f"{market.country}/{market.language}/{selected_source} market；"
                    "这不代表 DataForSEO 其他 API 不支持该地区"
                ),
            )

        raw_location, raw_language = selected
        location_code = _int(raw_location.get("location_code"))
        if location_code is None:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_MARKET_UNAVAILABLE, "DataForSEO Labs registry 缺少 location_code")
        language_code = str(raw_language.get("language_code") or "").strip()
        if not language_code:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_MARKET_UNAVAILABLE, "DataForSEO Labs registry 缺少 language_code")

        result = ProviderMarket(
            provider="dataforseo",
            capability=capability,
            supported=True,
            search_engine=selected_source,
            provider_country=market.country,
            location_code=location_code,
            location_name=str(raw_location.get("location_name") or market.country),
            language_code=language_code,
            resolution_source="dataforseo_labs_registry",
        )
        self._cache[key] = result
        return result


class SemrushMarketResolver:
    """Resolve version-specific Semrush market wire values without ISO guessing."""

    def __init__(self, v3_databases: dict[str, str] | None = None) -> None:
        self._v3_databases: dict[str, str] = {}
        if v3_databases:
            self._v3_databases.update(
                {_normalize_country(country): str(database).strip().lower() for country, database in v3_databases.items()}
            )

    def canonical_country(self, country: str) -> str:
        return _normalize_country(country)

    def v4_country(self, country: str) -> str:
        canonical = _normalize_country(country)
        # Current Semrush Keyword Metrics wire uses UK rather than ISO canonical GB.
        return "UK" if canonical == "GB" else canonical

    def v3_database(self, country: str) -> str:
        canonical = _normalize_country(country)
        database = self._v3_databases.get(canonical)
        if database:
            return database
        provider_country = "UK" if canonical == "GB" else canonical
        if provider_country not in _SEMRUSH_V3_PROVIDER_COUNTRIES:
            raise SeoDataError(SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                (
                    f"当前 Semrush v3 Domain Analytics coverage 未列出 {canonical}；"
                    "不能为未验证 market 猜 regional database"
                ),
            )
        return provider_country.lower()


def _normalize_country(value: str) -> str:
    clean = str(value or "").strip().upper()
    clean = _COUNTRY_ALIASES.get(clean, clean)
    if len(clean) != 2 or not clean.isalpha():
        raise SeoDataError(SeoDataErrorCode.INVALID_MARKET_INPUT, "market country 必须是 ISO 3166-1 alpha-2 国家码")
    return clean


def _normalize_language(value: str) -> str:
    clean = str(value or "").strip().replace("_", "-")
    if not clean:
        raise SeoDataError(SeoDataErrorCode.INVALID_MARKET_INPUT, "market language 必须显式提供，不能静默默认 en")
    parts = [part for part in clean.split("-") if part]
    if not parts or not re.fullmatch(r"[A-Za-z]{2,8}", parts[0]):
        raise SeoDataError(SeoDataErrorCode.INVALID_MARKET_INPUT, "market language 必须是有效 BCP47 language tag")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if re.fullmatch(r"[A-Za-z]{4}", part):
            normalized.append(part.title())
        elif re.fullmatch(r"[A-Za-z]{2}|\d{3}", part):
            normalized.append(part.upper())
        elif re.fullmatch(r"[A-Za-z0-9]{1,8}", part):
            normalized.append(part.lower())
        else:
            raise SeoDataError(SeoDataErrorCode.INVALID_MARKET_INPUT, "market language 必须是有效 BCP47 language tag")
    return "-".join(normalized)


def _normalize_search_engine(value: str) -> str:
    clean = str(value or "").strip().lower()
    if not clean or not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", clean):
        raise SeoDataError(SeoDataErrorCode.INVALID_MARKET_INPUT, "market search_engine 必须显式提供")
    return clean


def _select_provider_language(
    candidates: list[tuple[dict[str, object], dict[str, object]]],
    requested_language: str,
) -> tuple[dict[str, object], dict[str, object]] | None:
    requested = requested_language.lower()
    exact = [
        item
        for item in candidates
        if str(item[1].get("language_code") or "").strip().replace("_", "-").lower() == requested
    ]
    if len(exact) == 1:
        return exact[0]

    requested_base = requested.split("-", 1)[0]
    base_matches = [
        item
        for item in candidates
        if str(item[1].get("language_code") or "").strip().replace("_", "-").lower().split("-", 1)[0]
        == requested_base
    ]
    return base_matches[0] if len(base_matches) == 1 else None


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
