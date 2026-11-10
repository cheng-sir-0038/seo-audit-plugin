#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
UV_BIN="${UV_BIN:-uv}"

if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  printf '%s\n' 'uv 0.12.9 未安装。请执行：curl -LsSf https://astral.sh/uv/0.12.9/install.sh | sh' >&2
  exit 1
fi

UV_VERSION=$("$UV_BIN" --version | awk '{print $2}')
if [ "$UV_VERSION" != "0.12.9" ]; then
  printf '当前 uv %s；项目要求 uv 0.12.9。\n' "$UV_VERSION" >&2
  exit 1
fi

cd "$SCRIPT_DIR"

# 版本来源只有 pyproject.toml + uv.lock。Mac/Linux 会安装同一精确版本，
# 但由 uv 自动选择各平台自己的 wheel，避免手工维护两套依赖目录。
"$UV_BIN" sync --locked --group dev

printf 'Synced locked development environment: %s\n' "$SCRIPT_DIR/.venv"
