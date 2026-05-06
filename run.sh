#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export STOCK_APP_HOST="${STOCK_APP_HOST:-0.0.0.0}"
export STOCK_APP_PORT="${STOCK_APP_PORT:-8000}"

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "${PYTHON_BIN:-}" ]; then
  echo "找不到可用的 Python，請先安裝 python3 或建立 .venv。" >&2
  exit 1
fi

exec "$PYTHON_BIN" server.py
