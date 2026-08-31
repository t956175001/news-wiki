#!/usr/bin/env bash
# Nightly Postgres dump, kept on the VPS.
#
# This exists for the boring failure, not the dramatic one: a bad migration, a
# `flush` run against the wrong shell, or someone getting into /admin/ and
# quietly rewriting entries. Restoring is documented in docs/DEPLOYMENT.md —
# a backup nobody has ever restored is a hypothesis, not a backup.
#
# Install (as the deploy user):
#   crontab -e
#   17 3 * * *  /home/deploy/news-wiki/deploy/backup.sh >> /home/deploy/backups/backup.log 2>&1
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP=${KEEP:-7}

# shellcheck source=/dev/null
set -a && source "$REPO_DIR/.env" && set +a

mkdir -p "$BACKUP_DIR"
stamp=$(date +%Y%m%d-%H%M%S)
target="$BACKUP_DIR/newswiki-$stamp.sql.gz"

# --clean --if-exists so the dump can be replayed into a database that already
# has the schema, which is the situation in every restore that actually happens.
docker compose -f "$REPO_DIR/deploy/docker-compose.prod.yml" --env-file "$REPO_DIR/.env" \
    exec -T db pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip -9 > "$target"

# An empty or truncated dump is worse than none: it looks like a backup.
size=$(stat -c %s "$target")
if [ "$size" -lt 10240 ]; then
    echo "$(date -Is) FAIL dump is only ${size}B — keeping it for inspection, not rotating"
    exit 1
fi

# Rotate only after this run succeeded, so a broken night never deletes the
# last good copy.
ls -1t "$BACKUP_DIR"/newswiki-*.sql.gz | tail -n "+$((KEEP + 1))" | xargs -r rm --

echo "$(date -Is) OK  $target ($size bytes), keeping $KEEP"
