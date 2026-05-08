# Pakistan POS

> Hybrid offline-first + cloud-sync, FBR-compliant point-of-sale system for Pakistani retailers.

This is a three-app monorepo:

- **`backend/`** — Django 5 + DRF + PostgreSQL 16 + Redis 7 + Celery. Single source of truth.
- **`admin-web/`** — React + Vite + Tailwind + shadcn/ui. Owner / manager dashboard.
- **`pos-terminal/`** — Electron + React + better-sqlite3. Cashier terminal, runs offline.
- `customer-display/` — small static React app for the customer-facing second monitor (Phase 8).
- `shared/` — TypeScript types consumed by both frontends.

## Repo layout

```
pakistan-pos/
├── README.md                       ← you are here
├── PROJECT_PLAN.md                 ← vision, stack, phased roadmap (the contract)
├── DATABASE_SCHEMA.md              ← every Postgres table + index
├── SCREENS.md                      ← every cashier and admin screen
├── INTEGRATIONS.md                 ← FBR, payment methods, hardware
├── CLAUDE.md                       ← guidance for AI-assisted development
├── CLAUDE_CODE_PROMPTS.md          ← phase-by-phase prompts
├── CHANGELOG.md
├── docker-compose.yml              ← postgres + redis + django + celery
├── .env.example                    ← root env consumed by docker-compose
├── backend/                        ← Django API
├── admin-web/                      ← React admin dashboard
├── pos-terminal/                   ← Electron + React POS
├── customer-display/               ← (Phase 8)
└── shared/                         ← shared TypeScript types
```

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose v2) for Postgres + Redis + Django.
- **Node.js 20.x LTS** for the two frontends. `nvm use` in each frontend folder picks up `.nvmrc`.
- **Python 3.12** is *not* required on the host — the backend runs in a container. Install it on the host only if you want to run `manage.py` or `pytest` outside docker.

## First-time setup

```bash
# 1. Clone (already done if you're reading this).
# 2. Create a root .env with a real Django secret.
cp .env.example .env
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env
# Edit .env to remove the placeholder DJANGO_SECRET_KEY line.

# 3. Bring everything up.
docker compose up -d --build

# 4. Apply migrations.
docker compose exec backend python manage.py migrate

# 5. Create a superuser (also a fully-functional User).
docker compose exec backend python manage.py createsuperuser

# 6. Open the Django admin and create one Tenant + a TenantMembership for your superuser:
#    http://localhost:8000/admin/

# 7. Frontends — install + run, in separate terminals.
( cd admin-web    && npm install && npm run dev )    # → http://localhost:5173
( cd pos-terminal && npm install && npm run dev )    # → opens an Electron window
```

## Running the apps

| App | Command | URL / window |
|---|---|---|
| Backend | `docker compose up backend` | http://localhost:8000 |
| Django admin | (above) | http://localhost:8000/admin/ |
| Admin web | `npm run dev` in `admin-web/` | http://localhost:5173 |
| POS terminal | `npm run dev` in `pos-terminal/` | Electron window |

## Running tests

```bash
docker compose exec backend pytest             # backend
( cd admin-web && npm run lint && npm run typecheck )
( cd pos-terminal && npm run lint && npm run typecheck )
```

## Phase 0 caveats

This commit lands the Phase 0 foundation only. Notable gaps that are deliberate:

- **POS PIN login is online-only.** The cashier login posts to the backend; offline PIN login lands in Phase 3 with the sync engine.
- **Branches and terminals are not yet DB models.** The POS terminal reads `branch_name` and `terminal_name` from `pos-terminal/.env` for header rendering. They become real models in Phase 1.
- **`audit_log` and `sync_log` are not yet present.** Reserved per `DATABASE_SCHEMA.md` § 13. They appear when the features that need them appear (Phase 2 / Phase 3).
- **Catalog, sales, FBR, payments, returns, reports** — empty app folders reserve the layout; nothing is implemented. Each lands in its own phase per `CLAUDE_CODE_PROMPTS.md`.

## Where to read next

- `PROJECT_PLAN.md` — vision, stack choices and rejected alternatives, 16-week phased roadmap.
- `DATABASE_SCHEMA.md` — every table, field, index, tenancy rule.
- `SCREENS.md` — every cashier and admin screen with components, flows, animations.
- `INTEGRATIONS.md` — FBR/PRAL wire format, payment methods, hardware.
- `CLAUDE.md` — architecture invariants and review checklist for AI-assisted code.
- `CLAUDE_CODE_PROMPTS.md` — phase-by-phase prompts; one per phase.
