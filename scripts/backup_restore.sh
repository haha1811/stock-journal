#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${DB_PATH:-$ROOT_DIR/data/stock_journal.db}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$BACKUP_DIR"

cmd="${1:-}"
case "$cmd" in
  backup)
    ts="$(date +%Y%m%d_%H%M%S)"
    out="$BACKUP_DIR/stock_journal_${ts}.sqlite3"
    sqlite3 "$DB_PATH" ".backup '$out'"
    sha256sum "$out" > "$out.sha256"
    echo "backup_created=$out"
    ;;
  restore)
    src="${2:-}"
    [[ -n "$src" && -f "$src" ]] || { echo "usage: $0 restore /path/to/backup.sqlite3"; exit 1; }
    cp "$src" "$DB_PATH"
    echo "restored_from=$src"
    ;;
  list)
    ls -1t "$BACKUP_DIR"/stock_journal_*.sqlite3 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 {backup|restore|list}"
    exit 1
    ;;
esac
