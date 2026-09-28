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
# The DOWNLOAD-BUTTON copy. /download/terminal/ (nginx) serves a symlink
# /var/www/site/download/terminal/app -> THIS file, so a NEW installer only
# reaches new downloaders when this file is replaced too. Without this step the
# auto-update feed gets the new build but the download page keeps handing out the
# OLD .exe. (Django's download_terminal_app fallback reads the same path.)
DOWNLOAD_DEST="/srv/pos/backend/media/downloads/"

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

# --- Download-button copy: same .exe, so fresh downloads get the new build ----
echo "Refreshing the download-button installer → $HOST:$DOWNLOAD_DEST"
ssh -i "$KEY" -o ConnectTimeout=20 "$HOST" "mkdir -p $DOWNLOAD_DEST"
rsync -avz -e "ssh -i $KEY -o ConnectTimeout=20" \
  "$DIR"/invoiceSolution.exe \
  "$HOST:$DOWNLOAD_DEST"

ssh -i "$KEY" -o ConnectTimeout=20 "$HOST" \
  "chown -R pos:pos $DEST $DOWNLOAD_DEST && \
   echo '--- updates feed ---' && ls -la --time-style=+%Y-%m-%dT%H:%M $DEST && \
   echo '--- download installer ---' && ls -la --time-style=+%Y-%m-%dT%H:%M $DOWNLOAD_DEST"

# --- Dated download filename ------------------------------------------------
# The live download is served DIRECTLY by nginx (fast path), which sets a static
# Content-Disposition filename. Stamp today's build date into it so the saved
# file is e.g. invoiceSolution-4-Sep-2026.exe. The file on disk stays
# invoiceSolution.exe (symlink + auto-updater untouched). Django's fallback view
# already derives the same dated name from the .exe mtime, so both paths agree.
DL_NAME="invoiceSolution-$(date +%-d-%b-%Y).exe"
NGINX_CONF="/etc/nginx/sites-available/pos"
echo "Stamping download filename → $DL_NAME (nginx)"
ssh -i "$KEY" -o ConnectTimeout=20 "$HOST" "
  set -e
  cp -a '$NGINX_CONF' '$NGINX_CONF.bak-\$(date +%Y%m%d%H%M%S)'
  # Rewrite ONLY the invoiceSolution*.exe filename in the download location's
  # Content-Disposition (both server blocks), leaving everything else intact.
  sed -ri 's/(add_header Content-Disposition \"attachment; filename=)invoiceSolution[^\"]*\.exe/\1$DL_NAME/g' '$NGINX_CONF'
  nginx -t && systemctl reload nginx
  echo 'nginx reloaded; Content-Disposition now:'; grep -h 'filename=invoiceSolution' '$NGINX_CONF' | head -1
"

echo ""
echo "Published to BOTH the auto-update feed and the download button. Verify:"
echo "  curl -s https://client.invoicesolution.pk/updates/latest.yml    # auto-update manifest"
echo "  curl -sI https://client.invoicesolution.pk/download/terminal/    # filename=$DL_NAME + new Content-Length"
echo "Existing terminals self-update on next check (startup/hourly); new downloads get the new dated build immediately."
