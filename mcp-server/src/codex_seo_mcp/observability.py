from __future__ import annotations

import functools
import hashlib
import hmac
import inspect
import ipaddress
import json
import os
import secrets
import sys
import time
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar
from urllib.parse import urlsplit

from codex_seo_mcp.tool_boundary import SeoToolError

P = ParamSpec("P")
R = TypeVar("R", bound=dict[str, Any])

_DISABLED_VALUES = {"0", "false", "no", "off"}
_PRIVATE_HOST_SUFFIXES = (
    ".internal",
    ".invalid",
    ".lan",
    ".local",
    ".localhost",
    ".test",
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)
_FINGERPRINT_KEY = secrets.token_bytes(32)


def observability_enabled() -> bool:
    """Return whether safe MCP runtime events should be emitted to stderr."""

    return (os.getenv("SEO_OBSERVABILITY_ENABLED") or "1").strip().lower() not in _DISABLED_VALUES


def emit_event(event: str, /, **fields: object) -> None:
    """Emit one sanitized JSON event to stderr without touching MCP stdout.

    Callers must pass only low-risk metadata. This function deliberately has no raw payload/message
    argument so a Provider response or credential cannot be logged by accident through the common path.
    """

    if not observability_enabled():
        return

    payload: dict[str, object] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": _stable_text(event) or "unknown_event",
    }
    for key, value in fields.items():
        safe_value = _event_value(value)
        if safe_value is not None:
            payload[key] = safe_value
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        print(line, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        # 日志流关闭、管道断开或写入失败不能覆盖工具结果；也不能回退到 MCP stdout。
        return


def observe_tool(
    *,
    tool: str,
    capability: str | None = None,
    target_arg: str | None = None,
    strategy_arg: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Observe a public MCP Tool call while preserving its original callable signature."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            target = bound.arguments.get(target_arg) if target_arg else None
            strategy = bound.arguments.get(strategy_arg) if strategy_arg else None
            target_fields = _target_fields(target)
            request_fingerprint = _fingerprint(bound.arguments)

            emit_event(
                "tool_call_started",
                tool=tool,
                capability=capability,
                strategy=_stable_text(strategy),
                request_fingerprint=request_fingerprint,
                **target_fields,
            )
            started = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except SeoToolError as exc:
                emit_event(
                    "tool_call_failed",
                    tool=tool,
                    capability=capability,
                    strategy=_stable_text(strategy),
                    duration_ms=_duration_ms(started),
                    error_code=exc.seo_code,
                    request_fingerprint=request_fingerprint,
                    **target_fields,
                )
                raise
            except Exception:
                emit_event(
                    "tool_call_failed",
                    tool=tool,
                    capability=capability,
                    strategy=_stable_text(strategy),
                    duration_ms=_duration_ms(started),
                    error_code="unhandled_error",
                    request_fingerprint=request_fingerprint,
                    **target_fields,
                )
                raise

            result_fields = _result_fields(result)
            emit_event(
                "tool_call_completed",
                tool=tool,
                capability=capability,
                strategy=_stable_text(strategy),
                duration_ms=_duration_ms(started),
                request_fingerprint=request_fingerprint,
                # 每次调用更新的抓取时间不是新证据；data 内的业务时间仍参与比较。
                result_fingerprint=_fingerprint(
                    {key: value for key, value in result.items() if key != "fetched_at"}
                ),
                **result_fields,
                **target_fields,
            )
            return result

        return wrapped

    return decorator


def _duration_ms(started: float) -> float:
    return round(max(0.0, (time.perf_counter() - started) * 1000), 3)


def _result_fields(result: dict[str, Any]) -> dict[str, object]:
    status = _stable_text(result.get("status")) or "unknown"
    fields: dict[str, object] = {"result_status": status}

    provider = _stable_text(result.get("provider"))
    if provider:
        fields["provider"] = provider

    warnings = result.get("warnings")
    if isinstance(warnings, list):
        fields["warning_count"] = len(warnings)

    return fields


def _target_fields(value: object) -> dict[str, str]:
    text = _target_text(value)
    if not text:
        return {}

    fields = {"target_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}
    try:
        parsed = urlsplit(text)
    except ValueError:
        return fields

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return fields

    hostname = parsed.hostname.lower().rstrip(".")
    if _safe_public_hostname(hostname):
        fields["target_host"] = hostname
    return fields


def _safe_public_hostname(hostname: str) -> bool:
    if not hostname or hostname == "localhost" or hostname.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return address.is_global


def _stable_text(value: object) -> str | None:
    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value).strip()
    return text[:128] if text else None


def _target_text(value: object) -> str | None:
    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value).strip()
    return text if text else None


def _event_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        return text[:256] if text else None
    return None


def _fingerprint(value: object) -> str:
    """Create a process-local keyed digest without logging raw tool data."""

    normalized = _fingerprint_value(value)
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(
        _FINGERPRINT_KEY,
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:20]


def _fingerprint_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_fingerprint_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            text_key = str(key)
            if _sensitive_key(text_key):
                result[text_key] = "<redacted>"
            else:
                result[text_key] = _fingerprint_value(item)
        return result
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: (
                "<redacted>"
                if _sensitive_key(field.name)
                else _fingerprint_value(getattr(value, field.name))
            )
            for field in fields(value)
        }
    # Resolved dependency objects and runtime contexts are intentionally represented only by type.
    return {"type": type(value).__qualname__}


def _sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
