#!/usr/bin/env bash
# Daily encrypted backup → Backblaze B2.
#
# Cron entry:
#   15 2 * * * /srv/pos/deploy/scripts/backup_to_b2.sh >> /var/log/pos/backup.log 2>&1
#
# Required env (set via /etc/pos/backup.env, sourced below):
#   B2_BUCKET           — bucket name
#   B2_KEY_ID, B2_APP_KEY  — application key (NOT the master key)
#   GPG_RECIPIENT       — fingerprint of a key whose secret lives off-server
#   PGUSER, PGDATABASE, PGHOST, PGPORT
#
# Retention:
#   Weekly  → keep 4 weeks   on B2 lifecycle rule
#   Monthly → keep 12 months on B2 lifecycle rule
# Configure both as B2 lifecycle rules; this script just uploads.

set -euo pipefail

# shellcheck disable=SC1091
source /etc/pos/backup.env

ts=$(date -u +%Y-%m-%dT%H-%M-%SZ)
backup_dir=$(mktemp -d /tmp/pos-backup-XXXXXX)
trap 'rm -rf "$backup_dir"' EXIT

# 1. pg_dump in custom format (smaller + parallel-restore-friendly).
echo "[$(date -u)] Dumping postgres..."
pg_dump --format=custom \
    --host="$PGHOST" --port="$PGPORT" \
    --username="$PGUSER" --dbname="$PGDATABASE" \
    --file="$backup_dir/$ts.dump"

# 2. Encrypt with GPG to a public-key recipient. The secret key MUST
#    live off this server — otherwise compromise of the box compromises
#    the backups too.
echo "[$(date -u)] Encrypting..."
gpg --batch --yes --trust-model always \
    --output "$backup_dir/$ts.dump.gpg" \
    --encrypt --recipient "$GPG_RECIPIENT" \
    "$backup_dir/$ts.dump"

# 3. Upload to B2. The b2 CLI reads B2_KEY_ID + B2_APP_KEY from env.
echo "[$(date -u)] Uploading to B2..."
b2 authorize-account "$B2_KEY_ID" "$B2_APP_KEY" >/dev/null
b2 upload-file --noProgress \
    "$B2_BUCKET" \
    "$backup_dir/$ts.dump.gpg" \
    "daily/$ts.dump.gpg"

echo "[$(date -u)] Done."
