#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# 本地开发时允许从未提交的 .env.local 注入 Provider/OAuth 凭据；公开 Plugin 不把
# Secret 写进 mcp.json。Host 若已提供环境变量，则 shell 后加载的同名本地配置只用于开发。
if [ -f "$PLUGIN_ROOT_DIR/.env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PLUGIN_ROOT_DIR/.env.local"
  set +a
fi

# 插件缓存不能依赖开发目录复制来的 .venv；由 uv 按锁文件建立/校验当前环境。
# 安装输出必须走 stderr，stdout 只承载 MCP 协议。
"$SCRIPT_DIR/install-dev.sh" >&2

PYTHON="$SCRIPT_DIR/.venv/bin/python"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# 业务上 MCP 只负责数据能力，不在这里启动第二套 Agent/LLM Runtime。
exec "$PYTHON" -m codex_seo_mcp.server
