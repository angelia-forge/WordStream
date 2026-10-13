#!/bin/sh
set -eu

database_path=${1:-/data/wordstream.db}
backup_directory=${2:-/data/backups}

if [ ! -f "$database_path" ]; then
    echo "Database does not exist: $database_path" >&2
    exit 1
fi

mkdir -p "$backup_directory"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="$backup_directory/wordstream-$timestamp.db"

sqlite3 "$database_path" \
    "PRAGMA busy_timeout=5000; PRAGMA wal_checkpoint(TRUNCATE);" \
    >/dev/null
cp "$database_path" "$backup_path"

integrity=$(sqlite3 "$backup_path" "PRAGMA integrity_check;")
if [ "$integrity" != "ok" ]; then
    rm -f "$backup_path"
    echo "Backup integrity check failed: $integrity" >&2
    exit 1
fi

echo "$backup_path"
