from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.models.organic_visibility import (
    OrganicVisibility,
    OrganicVisibilitySnapshot,
)


@dataclass(slots=True)
class OrganicVisibilitySnapshotConfig:
    root: Path
    enabled: bool = True
    retention_weeks: int = 104

    @classmethod
    def from_env(cls) -> "OrganicVisibilitySnapshotConfig":
        plugin_data = Path(os.getenv("PLUGIN_DATA") or ".local")
        root = Path(
            os.getenv("ORGANIC_VISIBILITY_SNAPSHOT_DIR")
            or plugin_data / "snapshots" / "organic-visibility"
        )
        enabled = (os.getenv("ORGANIC_VISIBILITY_SNAPSHOTS_ENABLED") or "1").strip().lower()
        try:
            retention = int(os.getenv("ORGANIC_VISIBILITY_SNAPSHOT_RETENTION_WEEKS") or "104")
        except ValueError:
            retention = 104
        return cls(
            root=root,
            enabled=enabled not in {"0", "false", "no", "off"},
            retention_weeks=max(1, min(retention, 520)),
        )


class OrganicVisibilitySnapshotStore:
    """Persist one aggregate observation per ISO week and provider/market bucket.

    The store records what the plugin actually observed. It never manufactures missing weeks and it
    never rewrites provider monthly history into weekly rows.
    """

    def __init__(self, config: OrganicVisibilitySnapshotConfig | None = None) -> None:
        self.config = config or OrganicVisibilitySnapshotConfig.from_env()

    def record(
        self,
        result: CapabilityResult[OrganicVisibility],
        *,
        observed_at: datetime | None = None,
    ) -> OrganicVisibilitySnapshot | None:
        if not self.config.enabled or result.data.overview is None:
            return None

        now = observed_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)
        iso = now.isocalendar()
        week = f"{iso.year:04d}-W{iso.week:02d}"
        overview = result.data.overview
        snapshot = OrganicVisibilitySnapshot(
            week=week,
            observed_at=now.isoformat(),
            provider=result.provider,
            provider_data_updated_at=result.data.observation.data_updated_at,
            total_keywords=overview.total_keywords,
            top3_keywords=overview.top3_keywords,
            top10_keywords=overview.top10_keywords,
            top100_keywords=overview.top100_keywords,
            estimated_traffic=overview.estimated_traffic,
            new_keywords=overview.new_keywords,
            up_keywords=overview.up_keywords,
            down_keywords=overview.down_keywords,
            lost_keywords=overview.lost_keywords,
        )

        bucket = self._bucket_dir(
            target=result.data.target,
            target_scope=result.data.target_scope,
            country=result.data.market.country,
            language=result.data.market.language,
            provider=result.provider,
        )
        bucket.mkdir(parents=True, exist_ok=True)
        payload = {
            "target": result.data.target,
            "target_scope": result.data.target_scope,
            "country": result.data.market.country,
            "language": result.data.market.language,
            "provider": result.provider,
            "snapshot": asdict(snapshot),
        }
        self._atomic_json_write(bucket / f"{week}.json", payload)
        self._prune(bucket)
        return snapshot

    def recent(
        self,
        *,
        target: str,
        target_scope: str,
        country: str,
        language: str,
        provider: str,
        weeks: int = 8,
    ) -> list[OrganicVisibilitySnapshot]:
        if not self.config.enabled:
            return []
        limit = max(1, min(int(weeks), self.config.retention_weeks))
        bucket = self._bucket_dir(
            target=target,
            target_scope=target_scope,
            country=country,
            language=language,
            provider=provider,
        )
        if not bucket.exists():
            return []

        snapshots: list[OrganicVisibilitySnapshot] = []
        for path in sorted(bucket.glob("????-W??.json"), reverse=True):
            item = self._read_snapshot(path)
            if item is not None:
                snapshots.append(item)
            if len(snapshots) >= limit:
                break
        snapshots.reverse()
        return snapshots

    def _bucket_dir(
        self,
        *,
        target: str,
        target_scope: str,
        country: str,
        language: str,
        provider: str,
    ) -> Path:
        canonical = "\0".join(
            [
                target.strip().lower(),
                target_scope.strip().lower(),
                country.strip().upper(),
                language.strip().lower(),
                provider.strip().lower(),
            ]
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return self.config.root / digest

    def _read_snapshot(self, path: Path) -> OrganicVisibilitySnapshot | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload.get("snapshot")
            if not isinstance(raw, dict):
                return None
            return OrganicVisibilitySnapshot(
                week=str(raw["week"]),
                observed_at=str(raw["observed_at"]),
                provider=str(raw["provider"]),
                provider_data_updated_at=_text(raw.get("provider_data_updated_at")),
                total_keywords=_int(raw.get("total_keywords")),
                top3_keywords=_int(raw.get("top3_keywords")),
                top10_keywords=_int(raw.get("top10_keywords")),
                top100_keywords=_int(raw.get("top100_keywords")),
                estimated_traffic=_float(raw.get("estimated_traffic")),
                new_keywords=_int(raw.get("new_keywords")),
                up_keywords=_int(raw.get("up_keywords")),
                down_keywords=_int(raw.get("down_keywords")),
                lost_keywords=_int(raw.get("lost_keywords")),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _atomic_json_write(self, path: Path, payload: dict[str, object]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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

    def _prune(self, bucket: Path) -> None:
        paths = sorted(bucket.glob("????-W??.json"), reverse=True)
        for path in paths[self.config.retention_weeks :]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
