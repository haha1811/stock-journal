#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export STOCK_APP_HOST="${STOCK_APP_HOST:-0.0.0.0}"
export STOCK_APP_PORT="${STOCK_APP_PORT:-8000}"

exec "$SCRIPT_DIR/.venv/bin/python" server.py
