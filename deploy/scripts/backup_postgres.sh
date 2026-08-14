#!/usr/bin/env bash
set -euo pipefail
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${BACKUP_DIR:=/var/backups/algobot}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
pg_dump --format=custom --no-owner --no-acl   --host="$POSTGRES_HOST" --username="$POSTGRES_USER" "$POSTGRES_DB"   > "$BACKUP_DIR/algobot_${STAMP}.dump"
find "$BACKUP_DIR" -type f -name 'algobot_*.dump' -mtime +14 -delete
echo "Backup created: $BACKUP_DIR/algobot_${STAMP}.dump"
