#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# 这个入口必须在用户浏览器所在的同一台宿主机运行，不能从远程容器代替执行。
if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  printf '%s\n' 'GSC OAuth 环境尚未同步，请先运行 ./mcp-server/install-dev.sh' >&2
  exit 1
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

if [ -f "$PLUGIN_ROOT/.env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PLUGIN_ROOT/.env.local"
  set +a
fi

exec "$PYTHON" -m codex_seo_mcp.auth_cli
