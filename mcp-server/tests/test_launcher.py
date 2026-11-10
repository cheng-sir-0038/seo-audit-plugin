"""Launcher contract: rebuild packaged environments without polluting MCP stdout."""

import os
from pathlib import Path
import shutil
import subprocess


def test_launcher_syncs_before_start_and_stops_on_sync_failure(tmp_path):
    source = Path(__file__).resolve().parents[1]
    server = tmp_path / "plugin with spaces" / "mcp-server"
    server.mkdir(parents=True)
    for name in ("run.sh", "install-dev.sh"):
        shutil.copy2(source / name, server / name)
    uv = tmp_path / "uv"
    uv.write_text('''#!/bin/sh
if [ "$1" = "--version" ]; then echo 'uv 0.12.9'; exit 0; fi
[ "$*" = 'sync --locked --group dev' ] || exit 9
echo syncing
[ "${FAIL_SYNC:-0}" = 0 ] || exit 7
mkdir -p .venv/bin
printf '#!/bin/sh\\necho mcp-started\\n' > .venv/bin/python
chmod +x .venv/bin/python
''')
    uv.chmod(0o755)
    env = {**os.environ, "UV_BIN": str(uv)}
    result = subprocess.run([str(server / "run.sh")], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "mcp-started\n"
    assert "syncing" in result.stderr
    result = subprocess.run([str(server / "run.sh")], cwd=tmp_path,
                            env={**env, "FAIL_SYNC": "1"}, capture_output=True, text=True)
    assert result.returncode == 7
    assert result.stdout == ""
