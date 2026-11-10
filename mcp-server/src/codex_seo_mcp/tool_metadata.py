from __future__ import annotations

from mcp_types import ToolAnnotations

# MCP annotations are discovery/UI hints only. Runtime admission is enforced separately.
READ_ONLY_OPEN_WORLD = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=True,
)

READ_ONLY_LOCAL = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)

EXTERNAL_AUTHORIZATION_ACTION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
