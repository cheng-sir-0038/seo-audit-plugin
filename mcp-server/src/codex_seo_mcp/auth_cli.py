from __future__ import annotations

import asyncio
import json

from codex_seo_mcp.auth.google_oauth import GscAuthManager
from codex_seo_mcp.errors import SeoDataError


def main() -> None:
    """在当前宿主机执行一次 GSC Desktop OAuth。

    这个入口专门用于“浏览器和 OAuth 进程必须共享同一台主机 loopback”的场景。
    例如开发者在 macOS 上运行它时，Google 回调到 127.0.0.1 才会回到同一个 Python
    进程；不要从远程容器替用户执行这条命令。
    """

    try:
        result = asyncio.run(GscAuthManager().authorize())
    except SeoDataError as exc:
        print(json.dumps({"status": "error", "error": exc.to_dict()}, ensure_ascii=False))
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
