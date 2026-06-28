#!/bin/bash
# POS System Update Script
# Usage: ./update.sh [--source=/path/to/usb|git]
# Backs up DB, pulls update, restarts service, keeps last 3 DB backups.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"
DB_PATH="${POS_DB_PATH:-${SCRIPT_DIR}/pos.db}"
KEEP_BACKUPS=3
SERVICE_NAME="pos.service"
SOURCE="${1:-git}"

mkdir -p "$BACKUP_DIR"

echo "=== POS Update Script ==="

# Phase 1: Backup database
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/pos_pre_update_${TIMESTAMP}.db"

if [ -f "$DB_PATH" ]; then
    echo "Backing up database to ${BACKUP_FILE}..."
    sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'" 2>/dev/null || {
        echo "ERROR: Database backup failed" >&2
        exit 1
    }
    INTEGRITY=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>/dev/null)
    if [ "$INTEGRITY" != "ok" ]; then
        echo "ERROR: Backup integrity check failed" >&2
        rm -f "$BACKUP_FILE"
        exit 1
    fi
    echo "Backup OK (integrity verified)"
else
    echo "WARNING: No database found at ${DB_PATH}, skipping backup"
fi

# Phase 2: Apply update
ROLLBACK_NEEDED=false

if [ "$SOURCE" = "git" ]; then
    echo "Pulling latest code from git..."
    cd "$SCRIPT_DIR"
    git fetch --tags 2>/dev/null || echo "Warning: git fetch failed"
    if ! git pull 2>/dev/null; then
        echo "ERROR: git pull failed" >&2
        ROLLBACK_NEEDED=true
    else
        echo "Git pull completed"
    fi
elif [[ "$SOURCE" = --source=* ]]; then
    USB_PATH="${SOURCE#--source=}"
    if [ ! -d "$USB_PATH" ]; then
        echo "ERROR: USB source directory not found: ${USB_PATH}" >&2
        ROLLBACK_NEEDED=true
    else
        echo "Syncing from USB: ${USB_PATH}..."
        if ! rsync -av --delete --exclude='pos.db' --exclude='backups/' --exclude='logs/' --exclude='data/' --exclude='venv/' --exclude='.git/' "${USB_PATH}/" "${SCRIPT_DIR}/"; then
            echo "ERROR: USB sync failed" >&2
            ROLLBACK_NEEDED=true
        else
            echo "USB sync completed"
        fi
    fi
else
    echo "WARNING: Unknown source '${SOURCE}', skipping update"
fi

if [ "$ROLLBACK_NEEDED" = true ]; then
    if [ -f "$BACKUP_FILE" ]; then
        echo "Rolling back database from ${BACKUP_FILE}..."
        cp "$BACKUP_FILE" "$DB_PATH"
        echo "Rollback complete. Update aborted."
    else
        echo "ERROR: No backup available for rollback" >&2
    fi
    exit 1
fi

# Phase 3: Install/update Python dependencies
if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
    echo "Updating Python dependencies..."
    if [ -d "${SCRIPT_DIR}/venv" ]; then
        "${SCRIPT_DIR}/venv/bin/python" -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q 2>/dev/null || echo "Warning: pip install failed (non-fatal)"
    fi
fi

# Phase 4: Cleanup old backups (keep KEEP_BACKUPS most recent)
echo "Cleaning old backups (keeping ${KEEP_BACKUPS})..."
ls -t "${BACKUP_DIR}"/pos_pre_update_*.db 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | while read old; do
    rm -f "$old"
    echo "  Removed: $(basename "$old")"
done

# Phase 5: Restart service
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "Restarting ${SERVICE_NAME}..."
    systemctl restart "$SERVICE_NAME"
    echo "Service restarted"
elif [ -f "${SCRIPT_DIR}/venv/bin/python" ]; then
    echo "Service not managed by systemd. Kill and restart manually:"
    echo "  pkill -f app.py; sleep 1; cd ${SCRIPT_DIR} && source venv/bin/activate && python app.py &"
else
    echo "Update applied. Restart the service manually."
fi

echo "=== Update complete ==="
