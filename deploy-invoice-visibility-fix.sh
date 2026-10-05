#!/usr/bin/env bash
#
# Deploy the fix for: paid restaurant invoices never reaching the client admin.
#
# Root cause: at Charge the terminal fired sync.kick() (async) and
# voidOpenOrder() (immediate) against the same client_uuid. The void won the
# race and soft-deleted the sale the guest had just paid for.
#
# Ships three backend changes + one recovery command, then restarts BOTH
# services (the Celery worker runs FBR submit; deploying without restarting it
# leaves stale code running).
#
# Usage:  ./deploy-invoice-visibility-fix.sh
#
set -euo pipefail

HOST=root@167.233.19.109
KEY=~/.ssh/pos_deploy
REMOTE=/srv/pos/backend
SSH="ssh -i $KEY -o BatchMode=yes"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

say "1/5  Backing up the files being replaced"
$SSH "$HOST" "
  set -e
  STAMP=\$(date +%Y%m%d-%H%M%S)
  mkdir -p /root/pos-backups/\$STAMP
  cp $REMOTE/apps/sales/services/checkout.py   /root/pos-backups/\$STAMP/
  cp $REMOTE/apps/restaurant/services.py       /root/pos-backups/\$STAMP/
  echo \"backup: /root/pos-backups/\$STAMP\"
"

say "2/5  Uploading fixes"
scp -i "$KEY" -o BatchMode=yes \
  backend/apps/sales/services/checkout.py \
  "$HOST:$REMOTE/apps/sales/services/checkout.py"
scp -i "$KEY" -o BatchMode=yes \
  backend/apps/restaurant/services.py \
  "$HOST:$REMOTE/apps/restaurant/services.py"
scp -i "$KEY" -o BatchMode=yes \
  backend/apps/sales/management/commands/repair_paid_held_invoices.py \
  "$HOST:$REMOTE/apps/sales/management/commands/repair_paid_held_invoices.py"

say "3/5  Verifying the fixes actually landed"
$SSH "$HOST" "
  set -e
  grep -q 'deleted_at = None' $REMOTE/apps/sales/services/checkout.py \
    && echo 'OK  checkout.py  un-delete on finalize'
  grep -q 'tenant_id=tenant_id, client_uuid=client_uuid' $REMOTE/apps/sales/services/checkout.py \
    && echo 'OK  checkout.py  tenant-scoped lookup'
  grep -q 'payments.filter(status=\"completed\")' $REMOTE/apps/restaurant/services.py \
    && echo 'OK  restaurant/services.py  paid-order void guard'
"

say "4/5  Restarting services (backend AND celery worker)"
$SSH "$HOST" "
  set -e
  systemctl restart pos-backend.service
  systemctl restart pos-celery-worker.service
  sleep 3
  systemctl is-active pos-backend.service pos-celery-worker.service
"

say "5/5  Recovery dry run (reports only; writes nothing)"
$SSH "$HOST" "
  cd $REMOTE
  set -a; . /etc/pos/backend.env; set +a
  /srv/pos/venv/bin/python manage.py repair_paid_held_invoices 2>&1 | grep -viE 'warning|warn\('
"

cat <<'NOTE'

------------------------------------------------------------------
Deployed. The bug can no longer destroy a paid sale.

The dry run above lists invoices that are PAID but hidden. To
recover them (clears is_held / deleted_at only — nothing deleted):

    ssh -i ~/.ssh/pos_deploy root@167.233.19.109
    cd /srv/pos/backend
    set -a; . /etc/pos/backend.env; set +a
    /srv/pos/venv/bin/python manage.py repair_paid_held_invoices --apply

Rollback, if ever needed (path printed in step 1):

    cp /root/pos-backups/<STAMP>/*.py  back to their locations
    systemctl restart pos-backend pos-celery-worker
------------------------------------------------------------------
NOTE
