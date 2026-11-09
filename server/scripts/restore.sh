#!/usr/bin/env bash
# Restores a pg_dump custom-format backup into a (new) target database —
# the "tested restore" plan section 19 requires before launch.
#
# Usage: scripts/restore.sh <dump-file> <target-db-name>
# Creates <target-db-name> (must not already exist) and restores into it.
set -euo pipefail

file="$1"
target_db="$2"

if [ -z "$file" ] || [ -z "$target_db" ]; then
  echo "usage: $0 <dump-file> <target-db-name>" >&2
  exit 1
fi

createdb "$target_db"
pg_restore --no-owner --dbname="$target_db" "$file"
echo "restored '$file' into database '$target_db'"
