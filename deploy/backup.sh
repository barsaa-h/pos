#!/bin/bash
# POS Database Backup Script
# Usage: ./deploy/backup.sh
# Add to crontab: 0 */6 * * * /opt/pos/deploy/backup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POS_DIR="${POS_DIR:-$(dirname "$SCRIPT_DIR")}"
BACKUP_DIR="${POS_DIR}/backups"
DB_PATH="${POS_DB_PATH:-${POS_DIR}/pos.db}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/pos_backup_${TIMESTAMP}.db"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH" >&2
    exit 1
fi

sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'" 2>/dev/null || {
    echo "ERROR: sqlite3 backup failed" >&2
    rm -f "$BACKUP_FILE"
    exit 1
}

INTEGRITY=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>/dev/null)
if [ "$INTEGRITY" != "ok" ]; then
    echo "ERROR: Backup integrity check failed: $INTEGRITY" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

gzip -f "$BACKUP_FILE"
BACKUP_SIZE=$(du -h "${BACKUP_FILE}.gz" | cut -f1)

echo "Backup completed: ${BACKUP_FILE}.gz (${BACKUP_SIZE})"

find "$BACKUP_DIR" -name "pos_backup_*.db.gz" -mtime "+${KEEP_DAYS}" -delete 2>/dev/null || true
echo "Cleaned up backups older than ${KEEP_DAYS} days"
