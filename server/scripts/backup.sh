#!/usr/bin/env bash
# Daily Postgres backup (plan section 19: "Backups: daily pg_dump (or
# managed backups) to off-server storage, retention at least 14 days").
#
# Usage: PG_DSN=postgresql://user@host/dbname scripts/backup.sh
# PG_DSN uses plain libpq syntax (postgresql://...), not the
# postgresql+asyncpg:// form app/core/config.py uses for the app itself —
# pg_dump doesn't understand the +asyncpg driver suffix.
#
# "Off-server storage": this script only writes locally to $BACKUP_DIR.
# Shipping that file off the server (S3, GCS, etc.) is a one-line `aws s3
# cp`/`gsutil cp`/`rclone copy` added to whatever cron/CI runs this — left
# out here since it depends entirely on which provider the real deployment
# uses, which doesn't exist yet in this environment.
set -euo pipefail

PG_DSN="${PG_DSN:-postgresql://ramsi@/alphago_dev}"
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$0")/../backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$BACKUP_DIR/alphago_${stamp}.dump"

pg_dump --format=custom --file="$file" "$PG_DSN"
echo "backed up to $file"

find "$BACKUP_DIR" -name 'alphago_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete
