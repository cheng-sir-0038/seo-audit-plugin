from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProviderCacheConfig:
    """Local short-lived cache for paid/remote provider responses.

    Cache is runtime infrastructure under PLUGIN_DATA. It is intentionally separate from weekly
    SEO snapshots: cache avoids duplicate paid requests; snapshots preserve long-term observations.
    """

    root: Path
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "ProviderCacheConfig":
        plugin_data = Path(os.getenv("PLUGIN_DATA") or ".local")
        root = Path(
            os.getenv("PROVIDER_CACHE_DIR")
            or plugin_data / "cache" / "providers"
        )
        flag = (os.getenv("PROVIDER_CACHE_ENABLED") or "1").strip().lower()
        return cls(root=root, enabled=flag not in {"0", "false", "no", "off"})


class ProviderCache:
    """JSON file cache keyed by provider + operation + normalized request.

    Secrets must not be included in `request_key`. Cache misses/corruption never become provider
    errors; callers simply fall through to the remote API.
    """

    def __init__(self, config: ProviderCacheConfig | None = None) -> None:
        self.config = config or ProviderCacheConfig.from_env()

    def get(
        self,
        *,
        provider: str,
        operation: str,
        request_key: object,
        now: datetime | None = None,
    ) -> Any | None:
        if not self.config.enabled:
            return None
        path = self._path(provider=provider, operation=operation, request_key=request_key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        expires_at = _parse_time(payload.get("expires_at"))
        current = _utc(now)
        if expires_at is None or current >= expires_at:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        return payload.get("value")

    def set(
        self,
        *,
        provider: str,
        operation: str,
        request_key: object,
        value: object,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> None:
        if not self.config.enabled or ttl_seconds <= 0:
            return
        current = _utc(now)
        path = self._path(provider=provider, operation=operation, request_key=request_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "cached_at": current.isoformat(),
                "expires_at": (current + timedelta(seconds=ttl_seconds)).isoformat(),
                "value": value,
            }
            self._atomic_write(path, payload)
        except (OSError, TypeError, ValueError, OverflowError):
            # Cache is an optimization only. A disk/cache failure must never turn a successful
            # provider request into a failed SEO capability.
            return

    def clear(self, *, provider: str, operation: str | None = None) -> None:
        """Best-effort invalidation for one provider or one provider operation.

        Authentication changes are one of the few cases where a valid cached payload can belong
        to the wrong user context. Clearing is therefore explicit instead of encoding credentials
        or tokens into cache keys.
        """

        if not self.config.enabled:
            return
        path = self.config.root / _safe_segment(provider)
        if operation is not None:
            path /= _safe_segment(operation)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            # Cache invalidation must not turn a successful OAuth operation into a failed one.
            return

    def _path(self, *, provider: str, operation: str, request_key: object) -> Path:
        canonical = json.dumps(
            request_key,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(
            f"{provider.lower()}\0{operation}\0{canonical}".encode("utf-8")
        ).hexdigest()
        safe_provider = _safe_segment(provider)
        safe_operation = _safe_segment(operation)
        return self.config.root / safe_provider / safe_operation / f"{digest}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, object]) -> None:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value) or "unknown"


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None
