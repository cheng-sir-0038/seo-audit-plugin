from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec

from mcp.server.mcpserver.exceptions import ToolError

from codex_seo_mcp.errors import SeoDataError

P = ParamSpec("P")


class SeoToolError(ToolError):
    """Expected MCP Tool failure with one stable cross-Provider SEO error code."""

    def __init__(self, error: SeoDataError) -> None:
        self.seo_code = error.code.value
        self.seo_message = error.message
        super().__init__(f"[{self.seo_code}] {self.seo_message}")


def as_tool_error(error: SeoDataError) -> SeoToolError:
    return SeoToolError(error)


def map_seo_data_errors(
    func: Callable[P, Awaitable[dict[str, Any]]],
) -> Callable[P, Awaitable[dict[str, Any]]]:
    """Map stable data-layer failures onto MCP's native `isError` Tool result path.

    Successful tools keep structured output. Expected failures raise `ToolError`, so MCP marks the
    call as `isError=true` and places the stable error code/message in model-visible content. We do
    not return an application-level `{status: error}` payload because that would look successful at
    the MCP protocol layer.
    """

    @wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except SeoDataError as exc:
            raise as_tool_error(exc) from exc

    return wrapped
