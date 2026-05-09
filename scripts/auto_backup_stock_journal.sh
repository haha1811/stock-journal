#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/mnt/ssd/workspace/stock-journal"
DB_PATH="$ROOT_DIR/data/stock-records.sqlite3"
BACKUP_DIR="$ROOT_DIR/backups"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/backup.log"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') backup start ====="
  DB_PATH="$DB_PATH" BACKUP_DIR="$BACKUP_DIR" "$ROOT_DIR/scripts/backup_restore.sh" backup
  find "$BACKUP_DIR" -type f \( -name 'stock_journal_*.sqlite3' -o -name 'stock_journal_*.sqlite3.sha256' \) -mtime +"$RETENTION_DAYS" -print -delete
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') backup done ====="
} >> "$LOG_FILE" 2>&1
