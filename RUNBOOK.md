# Runbook

Operational guide for the production deployment. If something is broken
and you need to fix it now, start here.

## Quick reference

| Symptom                                 | First check                                         |
|-----------------------------------------|-----------------------------------------------------|
| Site returns 502/504                    | `systemctl status pos-backend` |
| Sales aren't showing in admin web       | Celery worker — `systemctl status pos-celery-worker` |
| FBR submissions backing up              | `journalctl -u pos-celery-worker -n 200` for errors |
| Reports show stale numbers              | Beat scheduler — `systemctl status pos-celery-beat` |
| /api/health/ready returns 503           | DB or Redis is unreachable; check both              |
| Disk filling                            | Logs in `/var/log/pos/`, media in `/srv/pos/backend/media/` |

## Health endpoints

- `GET /api/health/`        — process is up. Used by HAProxy / Nginx liveness
- `GET /api/health/ready/`  — DB + Redis reachable. Used by k8s-style readiness
  probes; returns 503 if either dependency is degraded

UptimeRobot should hit `/api/health/ready/` with a 60-second interval. Page
the on-call when it fails three checks in a row.

## Restart procedure

After a code change pushed by GitHub Actions, the deploy workflow
restarts services automatically. To restart by hand:

```bash
sudo systemctl restart pos-backend
sudo systemctl restart pos-celery-worker
sudo systemctl restart pos-celery-beat
```

Order matters only if you are restarting all three: backend can stay up
while workers restart. Celery beat losing a few minutes is harmless;
it picks up the next scheduled tick.

## Logs

Structured Django request logs go to systemd journal:

```bash
journalctl -u pos-backend -f                    # follow live
journalctl -u pos-backend --since "1 hour ago"  # range
```

Each request line includes tenant_id and user_id, so to investigate
a specific tenant:

```bash
journalctl -u pos-backend --since today | grep "tenant=<uuid>"
```

Celery logs:

```bash
tail -f /var/log/pos/celery-worker.log
tail -f /var/log/pos/celery-beat.log
```

## FBR submission backed up

Symptom: `fbr_submissions` table growing fast, no recent rows with
`status_code='00'`.

1. Check whether PRAL is reachable from the VPS:
   ```bash
   curl -sS --max-time 10 https://gw.fbr.gov.pk
   ```
2. Check whether the IP changed. PRAL whitelists up to 3 static IPs;
   if your VPS migrated, register the new IP with PRAL before doing
   anything else.
3. Tail the worker logs for the actual error (token expired, network
   timeout, validation failure):
   ```bash
   journalctl -u pos-celery-worker -n 100 | grep -i fbr
   ```
4. Failed submissions retry with exponential backoff. Once the root
   cause is fixed, they drain on their own. To force-retry early,
   use the FBR submissions admin page or kick the Celery task by hand.

## Rolling back a deploy

The deploy workflow does `git reset --hard origin/main`. To roll
back:

```bash
ssh pos@<host>
cd /srv/pos
git log --oneline -10                 # find the previous good commit
git reset --hard <good-commit-sha>
cd backend
/srv/pos/venv/bin/python manage.py migrate --noinput
sudo systemctl restart pos-backend pos-celery-worker pos-celery-beat
```

If the bad deploy ran a forward migration, you may need to roll the
migration back too. Each migration includes a reverse, but never
roll back a migration that has already been replicated to terminals
(it will desync the schema across the fleet).

## Restoring from backup

Backups land in B2 daily at 02:15 PKT (`deploy/scripts/backup_to_b2.sh`).
To restore to a staging box:

```bash
# 1. Pull the latest backup file.
b2 sync b2://pos-backups/daily ./restore-tmp --threads 1

# 2. Decrypt — the GPG secret key must be on the staging box.
gpg --output restore.dump --decrypt restore-tmp/<latest>.dump.gpg

# 3. Drop & recreate the target DB.
sudo -u postgres psql -c "DROP DATABASE IF EXISTS pos_staging;"
sudo -u postgres psql -c "CREATE DATABASE pos_staging OWNER pos;"

# 4. Restore.
pg_restore --dbname=pos_staging --jobs=4 --no-owner --clean restore.dump
```

Drill this once a quarter on a real staging box. A backup that has
never been restored is not a backup.

## Postgres connection pool exhausted

If `pos-backend` logs `OperationalError: too many connections`:

1. Check current count:
   ```bash
   sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='pos';"
   ```
2. The systemd unit runs gunicorn with 3 workers. With 100
   `max_connections` and Celery + admin contributing, headroom is
   plenty — exhaustion suggests a leak or runaway query.
3. List long-running queries:
   ```bash
   sudo -u postgres psql -c "SELECT pid, now()-query_start AS age, state, query FROM pg_stat_activity WHERE datname='pos' ORDER BY age DESC NULLS LAST LIMIT 10;"
   ```
4. Cancel a stuck query: `SELECT pg_cancel_backend(<pid>);`. As a
   last resort, `pg_terminate_backend(<pid>)`.

## Adding a new tenant

```bash
ssh pos@<host>
cd /srv/pos/backend
/srv/pos/venv/bin/python manage.py createtenant \
    --business-name "Khalil General Store" \
    --ntn 1234567 \
    --owner-email khalil@example.com
```

The owner gets a one-time link to set their password; once they sign
in, the onboarding wizard walks them through branch + terminal +
products + first sale.

## Releasing a new POS terminal version

The Electron app auto-updates from GitHub Releases. To cut a new
build:

1. Bump `pos-terminal/package.json` version (`npm version patch` etc).
2. Push the tag: `git push origin v<x.y.z>`.
3. The `pos-release` GitHub Action builds Windows + Linux installers
   (and macOS dmg if Apple secrets are configured), signs them, and
   publishes to the releases channel.
4. Each cashier machine picks up the update on next app start. Sales
   in progress are not interrupted; install happens on next quit.

### Required CI secrets

| Secret | Purpose |
|---|---|
| `CSC_LINK` | Base64 of your `.p12` Windows cert OR `https://…` URL |
| `CSC_KEY_PASSWORD` | Cert password |
| `GH_TOKEN` | Token with `repo` scope on the releases repo |
| `APPLE_ID` | (mac only) Apple ID for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | (mac only) app-specific password |
| `APPLE_TEAM_ID` | (mac only) 10-char team ID |

If `CSC_LINK` is unset, the build still produces working installers
but they are unsigned. Don't ship unsigned to customers — Windows
SmartScreen will warn on first run.

### Rolling back a bad release

GitHub Releases supports marking a release as draft/pre-release.
Setting the latest release to "draft" pulls it from the auto-update
channel; existing installs won't downgrade automatically. Push a
new patch version with the fix to roll forward.

## Pre-launch checklist

Per `CLAUDE_CODE_PROMPTS.md` Phase 8 §10:

- [ ] 3 pilot shops running for 2 weeks
- [ ] daily syncs successful (sync health green for 14 consecutive days)
- [ ] all FBR submissions valid (zero non-retryable failures)
- [ ] cashier feedback positive (qualitative survey)
- [ ] critical-bug count = 0
- [ ] this RUNBOOK.md kept current
- [ ] rollback procedure tested (drill performed in last 30 days)
- [ ] backup-restore drill performed (drill performed in last 30 days)
- [ ] axe-core run on every admin page (no critical issues)
- [ ] Lighthouse run on admin web (≥ 90 in all categories)

## Out-of-scope for V1 ("if it breaks, accept it")

- Mobile apps (none exist; ignore)
- Multi-currency (Pakistani Rupee only)
- Loyalty programs
- E-commerce sync
- Restaurant features (KDS, table management)
- Provincial sales tax (SRB / PRA) — only federal FBR
- AI / recommendations

These are explicitly deferred per `PROJECT_PLAN.md` §13. If a customer
asks about one, route to V2 backlog.
