#!/usr/bin/env bash
# Publish a terminal build to the self-hosted auto-update feed so every installed
# terminal updates itself. Run AFTER the pos-build-exe CI produces the 3 files.
#
# Usage:
#   ./scripts/publish-update.sh <dir-with-artifacts>
#     where <dir> contains: invoiceSolution.exe, latest.yml, *.blockmap
#
# It rsyncs those to https://client.invoicesolution.pk/updates/ on the VPS.
# electron-updater on each terminal reads latest.yml (served no-cache), sees the
# new version, downloads the .exe, and the cashier gets the "Update ready" banner.
set -euo pipefail

DIR="${1:?Usage: publish-update.sh <dir-with-invoiceSolution.exe latest.yml *.blockmap>}"
HOST="root@167.233.19.109"
KEY="${SSH_KEY:-$HOME/.ssh/pos_deploy}"
DEST="/srv/pos/updates/"

for f in latest.yml invoiceSolution.exe; do
  [ -f "$DIR/$f" ] || { echo "ERROR: $DIR/$f not found"; exit 1; }
done

echo "Publishing update from $DIR → $HOST:$DEST"
# .exe + .blockmap + latest.yml. latest.yml LAST so a terminal never sees the new
# manifest before the .exe it points to is fully uploaded.
rsync -avz -e "ssh -i $KEY -o ConnectTimeout=20" \
  "$DIR"/invoiceSolution.exe "$DIR"/*.blockmap \
  "$HOST:$DEST"
rsync -avz -e "ssh -i $KEY -o ConnectTimeout=20" \
  "$DIR"/latest.yml \
  "$HOST:$DEST"

ssh -i "$KEY" -o ConnectTimeout=20 "$HOST" "chown -R pos:pos $DEST && ls -la --time-style=+%Y-%m-%dT%H:%M $DEST"
echo ""
echo "Published. Verify the feed:"
echo "  curl -s https://client.invoicesolution.pk/updates/latest.yml"
echo "Every terminal will pick it up on next check (startup or hourly)."
