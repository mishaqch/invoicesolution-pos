# Pakistan POS — Master Project Plan

> A hybrid (offline-first + cloud-sync), FBR-compliant POS system built for Pakistani retailers, restaurants, and pharmacies. Optimized for low-cost hosting, unreliable internet, modest hardware, and real tax compliance.

## Companion documents
- `DATABASE_SCHEMA.md` — every table, field, relationship, and index
- `SCREENS.md` — every cashier and admin screen with components and flows
- `INTEGRATIONS.md` — FBR/PRAL, payment methods (cash, card, EasyPaisa, JazzCash, Raast), and hardware (printers, scanners, drawer)

---

## 1. Vision & non-negotiables

We are building a POS that:

1. **Works offline.** Power outage? Internet down? The cashier keeps billing. Sync happens automatically when connectivity returns.
2. **Is FBR-compliant out of the box.** Built around the PRAL Digital Invoicing flow as documented in their v1.6 manual, including the 72-hour edit window and the 10% monthly cancel cap.
3. **Runs on cheap infrastructure.** Total monthly cloud cost under $20 for the first 100 customers. Self-hosted Django on a single VPS, no AWS, no managed databases.
4. **Is fast on modest hardware.** Targets a 2-core / 4 GB RAM Windows machine for the cashier terminal. Most cashier interactions complete in under 200ms locally.
5. **Looks professional.** Industry-standard design language (clean typography, generous whitespace, subtle motion). Not flashy — *trustworthy*.
6. **Is sellable.** Onboarding a new shop takes under 30 minutes. Cashier training takes under 30 minutes.

If a feature compromises any of the above six points, it doesn't ship in V1.

---

## 2. Design principles

**Offline-first by default.** Every cashier action writes to local SQLite first, then queues for sync. The UI never blocks waiting for the network. The cashier never sees a spinner unless they ask for something explicitly remote (like a report covering all branches).

**Single source of truth: PRAL.** Once an invoice is submitted to FBR, PRAL's response (the `FBR Invoice Number` and timestamps) is the authoritative record. Local data is a cache.

**Idempotency everywhere.** Every write operation carries a client-generated UUID so retries are safe. Networks fail mid-request — that's normal, not exceptional.

**Audit, don't delete.** Every state change in sales, inventory, and prices appends to an immutable audit log. Six-year retention is a legal requirement; build it from day one.

**Touch-first, keyboard-fast.** Cashiers use both. Big tap targets (44px minimum) plus full keyboard shortcuts for power users. Numeric keypad operations should be possible without leaving the home row.

**Sentence case, plain language, Urdu where it matters.** Buttons say "Add product" not "ADD PRODUCT". Receipts include Urdu line items where the customer expects them. No technical jargon in cashier-facing screens.

**Two-thousand customer rule.** If a design choice scales fine for 50 customers but breaks at 2000, redesign now. Multi-tenancy, per-tenant cancel-budget tracking, and per-tenant FBR tokens are designed in from V1.

---

## 3. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Backend framework | Django 5 + Django REST Framework | Mature, batteries-included (admin, auth, ORM, migrations), excellent for tax/audit-heavy systems |
| Backend database | PostgreSQL 16 (self-hosted) | Free, rock-solid, strong constraints, easy backup |
| Cache & queue | Redis 7 | Single binary, fits in 200 MB, handles sync queue and session cache |
| Background jobs | Celery + Redis broker | FBR submissions, sync, reports, scheduled tasks |
| Web admin | React 18 + Vite + Tailwind + shadcn/ui | Industry-standard, fast dev, tree-shakeable, free |
| State management | Zustand + TanStack Query | Lighter than Redux, server state separate from UI state |
| POS terminal | Electron + React (same component library as admin) | Native printer/scanner access, offline runtime, single codebase |
| Local DB on terminal | SQLite via better-sqlite3 | Embedded, zero-config, ACID, fast |
| Animation | Framer Motion (now `motion`) for React | 200–300ms ease-out transitions, spring physics for satisfying feedback |
| Icons | Lucide | Consistent, tree-shakeable, free |
| Charts | Recharts | Lightweight, composable, theme-aware |
| Receipt printing | node-thermal-printer (ESC/POS) | Works with 58mm and 80mm printers |
| Barcode scanning | USB HID (just keystrokes) — no library | Scanners emulate keyboards; treat as input |
| Web server | Nginx + Gunicorn | Standard, free, low memory |
| TLS | Let's Encrypt via Certbot | Free, auto-renew |
| Hosting | Contabo VPS (Germany) or Hetzner (Germany) — $5/month | Cheap, reliable, EU privacy. Static IPs included |
| File storage | Backblaze B2 ($0.005/GB/month) | Receipts, backups, product images |
| Email | Brevo (Sendinblue) free tier — 300/day | Sufficient for V1 transactional |
| SMS | Veevotech / local Pakistani provider | Rs. 0.40–0.60/SMS, supports Urdu |
| Error tracking | Sentry self-hosted OR Glitchtip (free) | Catch crashes in production |
| CI/CD | GitHub Actions free tier | 2000 minutes/month is plenty |

**Deliberately not chosen, with reasons:**

- *AWS / Azure / GCP* — overpriced for our scale. A managed Postgres alone is $25/month minimum.
- *Flutter / React Native* — V1 doesn't need a mobile app. Adding one means duplicate state management and another bug surface. V2.
- *Tauri instead of Electron* — Tauri is lighter, but the ESC/POS and HID library ecosystem on Tauri is thinner. Electron is the safer bet right now; revisit in V2.
- *NoSQL databases* — sales data is deeply relational with hard constraints. Postgres is the right tool.
- *Microservices* — single Django monolith for V1. Split out only when a specific service needs to scale independently.
- *Kubernetes* — single VPS + systemd is fine for the first 1,000 customers. Reach for k8s only when one machine isn't enough.

---

## 4. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CUSTOMER PREMISE                        │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ POS terminal #1  │  │ POS terminal #2  │   ◄─ Electron app   │
│  │  React + SQLite  │  │  React + SQLite  │      Local-first    │
│  └────────┬─────────┘  └────────┬─────────┘                     │
│           │                     │                               │
│           │   Local LAN (when both online, optional peer sync)  │
│           └─────────────────────┘                               │
│                     │                                           │
│        ┌────────────┴────────────┐                              │
│        │   Customer-facing       │  ◄─ Optional 2nd display     │
│        │   display (HTML page)   │                              │
│        └─────────────────────────┘                              │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTPS (idempotent sync API)
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                       OUR CLOUD (single VPS)                    │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                  Nginx (TLS, static)                    │   │
│   └─────────────────────────────────────────────────────────┘   │
│       │                    │                    │               │
│   ┌───▼─────┐         ┌────▼────┐          ┌────▼────┐          │
│   │ Django  │         │ Admin   │          │ POS     │          │
│   │ API     │         │ web app │          │ landing │          │
│   │ (DRF)   │         │ (React) │          │ + DL    │          │
│   └───┬─────┘         └─────────┘          └─────────┘          │
│       │                                                         │
│   ┌───▼──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│   │   PostgreSQL 16  │   │   Redis 7    │   │   Celery     │    │
│   │   (sales, fbr,   │   │  (queue+     │   │  (FBR sync,  │    │
│   │   inventory,     │   │   cache)     │   │   reports)   │    │
│   │   audit)         │   └──────────────┘   └──────────────┘    │
│   └──────────────────┘                                          │
│                                                                 │
│   Static IPs (1–3, declared to PRAL for whitelisting)           │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTPS to PRAL approved IPs only
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                       EXTERNAL SERVICES                         │
│                                                                 │
│   PRAL/FBR Digital Invoicing API   (sandbox + production)       │
│   Payment gateways: 1Link/NIFT, EasyPaisa, JazzCash, Raast      │
│   SMS gateway (Veevotech)                                       │
│   Email (Brevo)                                                 │
│   Object storage (Backblaze B2 — backups, receipts, images)     │
└─────────────────────────────────────────────────────────────────┘
```

### Why this shape

- **The customer's POS terminals never talk to PRAL directly.** All FBR traffic flows through our central server, which holds the static IPs whitelisted with PRAL. This is non-negotiable: PRAL's IP whitelisting (max 3 IPs) makes per-customer-direct integration impossible at scale.
- **Each terminal has its own SQLite.** A power cut on one terminal doesn't affect another. Terminals reconcile through the cloud, not directly with each other (except optional LAN peer-sync as a V2 nicety).
- **The customer-facing display is just an HTML page** served by the POS terminal's local Electron process on a second monitor. No separate process needed.
- **Single VPS for V1.** When we hit ~500 customers we add a read replica. When we hit ~2000 we move Postgres to a dedicated machine. Don't over-architect early.

### Data flow for a single sale (happy path)

1. Cashier scans items → POS adds to cart (local React state).
2. Cashier presses **Charge** → payment screen.
3. Cashier confirms cash payment → POS:
   - Writes invoice to local SQLite with `status = 'pending_sync'`.
   - Prints provisional receipt (no FBR Invoice Number yet) OR holds print until step 5 if online — configurable per shop.
   - Opens cash drawer.
   - Enqueues sync job.
4. Sync worker (background) POSTs to our Django API. API:
   - Validates buyer, items, taxes.
   - Posts to PRAL `postinvoicedata` endpoint with sandbox/production token.
   - Receives `FBR Invoice Number` + IRN.
   - Persists everything to Postgres with `status = 'valid'`.
   - Returns the FBR number to the POS.
5. POS receives response → updates local invoice to `status = 'valid'` with FBR number → if not yet printed, prints final receipt with FBR QR code.

If step 4 fails (network or PRAL error), the invoice stays in `pending_sync` and retries with exponential backoff (10s, 30s, 2min, 10min, 1hr, 6hr). Cashier sees a small amber dot on the invoice in their history. Persistent failures surface to the admin dashboard for manual review.

---

## 5. Project structure (monorepo)

```
pakistan-pos/
├── README.md                       ← this overview
├── PROJECT_PLAN.md                 ← this file
├── DATABASE_SCHEMA.md
├── SCREENS.md
├── INTEGRATIONS.md
├── CHANGELOG.md
├── docker-compose.yml              ← local dev (postgres + redis + django)
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       ├── admin-ci.yml
│       └── pos-build.yml           ← builds Electron installer
│
├── backend/                        ← Django API
│   ├── manage.py
│   ├── pyproject.toml
│   ├── apps/
│   │   ├── accounts/               ← users, roles, permissions
│   │   ├── tenants/                ← multi-tenancy, businesses
│   │   ├── catalog/                ← products, categories, units
│   │   ├── inventory/              ← stock, movements, transfers
│   │   ├── sales/                  ← invoices, items, payments
│   │   ├── customers/
│   │   ├── suppliers/
│   │   ├── purchases/
│   │   ├── returns/
│   │   ├── fbr/                    ← PRAL integration
│   │   ├── payments/               ← gateway integrations
│   │   ├── reports/
│   │   ├── sync/                   ← sync queue endpoints
│   │   ├── audit/
│   │   └── notifications/          ← email, SMS, in-app
│   ├── core/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   ├── prod.py
│   │   │   └── test.py
│   │   ├── celery.py
│   │   ├── middleware.py
│   │   └── permissions.py
│   └── tests/
│
├── admin-web/                      ← React admin dashboard
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                 ← one folder per top-level screen
│   │   ├── components/
│   │   │   ├── ui/                 ← shadcn primitives
│   │   │   ├── charts/
│   │   │   ├── forms/
│   │   │   └── layout/
│   │   ├── features/               ← feature-grouped logic
│   │   │   ├── products/
│   │   │   ├── sales/
│   │   │   ├── inventory/
│   │   │   ├── fbr/
│   │   │   └── reports/
│   │   ├── lib/                    ← api client, utils
│   │   ├── hooks/
│   │   └── stores/                 ← zustand stores
│   └── public/
│
├── pos-terminal/                   ← Electron + React POS
│   ├── package.json
│   ├── electron-builder.yml
│   ├── electron/
│   │   ├── main.ts                 ← Electron main process
│   │   ├── preload.ts
│   │   ├── printer.ts              ← thermal printer adapter
│   │   ├── scanner.ts              ← barcode scanner config
│   │   ├── drawer.ts               ← cash drawer trigger
│   │   ├── display.ts              ← customer-facing display
│   │   └── db/
│   │       ├── schema.sql
│   │       ├── migrations/
│   │       └── client.ts
│   └── src/                        ← React UI
│       ├── main.tsx
│       ├── routes/                 ← /sale, /reports, /settings, /day-close
│       ├── components/
│       ├── features/
│       ├── lib/
│       │   ├── sync.ts             ← outbound queue
│       │   └── offline-state.ts
│       └── stores/
│
├── customer-display/               ← HTML page for second monitor
│   └── (very small static React app)
│
└── shared/                         ← types shared across all 3 apps
    ├── types/
    │   ├── invoice.ts
    │   ├── product.ts
    │   ├── fbr.ts
    │   └── payment.ts
    └── constants/
```

**Why monorepo:** type definitions, validation schemas, and FBR JSON shapes are shared between all three apps. A single `shared/` folder with a TypeScript path alias eliminates a whole class of "does the API and POS agree on the field name?" bugs.

---

## 6. Development roadmap

Realistic timeline assuming one developer working with Claude Code, ~30 hours/week. **Total: 16 weeks to a sellable V1.** Faster if you cut scope.

### Phase 0 — Foundation (week 1)

- Repo scaffold, Docker compose for local dev (Postgres + Redis + Django).
- Django project skeleton with `accounts`, `tenants` apps.
- Multi-tenancy decision: schema-per-tenant via `django-tenants`, OR row-level via `tenant_id` foreign key. **Pick row-level for simplicity** unless you have a specific reason otherwise.
- Authentication: JWT for API, with refresh tokens. PIN-based fast-login for cashiers.
- Permission system: role-based (Owner, Manager, Cashier, Accountant) plus per-permission overrides.
- Admin web skeleton: Vite + React + Tailwind + shadcn/ui set up, login/logout, protected routes.
- POS terminal skeleton: Electron + React + SQLite running locally, talks to local API only.
- CI: GitHub Actions running tests on every PR.

**Exit criteria:** I can run `docker compose up`, register a tenant, log in to the admin, and open the POS app. All three talk to one database.

### Phase 1 — Catalog & inventory (weeks 2–3)

- Products: list, add, edit, delete, soft-delete, bulk import via CSV.
- Categories with parent-child nesting.
- Units of measure (kg, gm, litre, piece, dozen, box, etc.) — Pakistani standard set seeded by default.
- Tax rates (standard 18%, reduced rates by HS code).
- HS Code catalog (seed from FBR's published list — there are ~5000 codes).
- Inventory locations (per branch).
- Stock-in (manual receipt), stock-out, stock adjustment with reason.
- Stock transfer between branches with in-transit tracking.
- Low-stock alerts (per-product threshold, daily digest email).

**Exit criteria:** I can add 100 products, set stock levels, and the POS app sees them when offline.

### Phase 2 — Sales & cash payments (weeks 4–5)

- POS sale flow: scan/search → cart → cash payment → receipt print → drawer open.
- Local SQLite invoice creation with `pending_sync` status.
- Held sales (park & recall).
- Quick discount (% or amount) at line and cart level.
- Customer selection (registered or walk-in unregistered).
- Day open / day close with cash reconciliation.
- Receipt template (configurable header, footer, logo).
- Admin: sales list, sale detail, cancel sale (within rules), basic daily summary.
- ESC/POS thermal printer integration (58mm and 80mm).
- Barcode scanner support (USB HID, just keyboard input).

**Exit criteria:** Cashier can complete 10 sales offline, print receipts, balance the till at end of day. Sales appear in admin once back online.

### Phase 3 — Sync engine (week 6)

This is the hardest phase. Don't skip it.

- Idempotent sync API: every POS-side write has a client UUID, server is idempotent.
- Outbound queue on POS: persistent (SQLite), survives crashes.
- Retry with exponential backoff and jitter.
- Conflict resolution: last-write-wins for inventory, append-only for sales (sales never conflict — each is a new record).
- Sync status indicator in POS UI (dot in corner: green=synced, amber=syncing, red=error).
- Admin dashboard tile showing per-terminal sync health.

**Exit criteria:** I can pull the network cable mid-sale, finish the sale, plug it back in, and watch everything sync without intervention.

### Phase 4 — FBR integration, sandbox first (weeks 7–9)

- IRIS registration helper UI (we walk the customer through PRAL signup).
- Technical details form (collected once per shop, posted to PRAL).
- IP whitelisting management (we declare our static IPs for the customer).
- Sandbox token storage (encrypted at rest).
- JSON builder: convert our internal sale → PRAL JSON spec.
- Scenario test runner: cycle through SN001…SN015+ for the chosen sector.
- Production token activation flow.
- Live submission: sale → PRAL → FBR Invoice Number → store + display.
- 72-hour edit window enforcement (UI + backend).
- 10% monthly cancel-budget tracker (per tenant, per month).
- Cancel/edit invoice flow with the constraint matrix from the manual.
- QR code generation on receipt with FBR Invoice Number.
- Final receipt template matching PRAL's sample layout.

**Exit criteria:** End-to-end, a sale rings up offline, syncs when online, gets validated by PRAL sandbox, prints a compliant receipt with QR code. Cancel budget tracker correctly enforces the 10% rule across a multi-day test.

### Phase 5 — Multi-payment methods (week 10)

- Card payment (manual reference number entry — physical card terminal is separate device).
- EasyPaisa: static merchant QR display + manual confirmation. Merchant API integration as V1.5 if onboarding completes.
- JazzCash: same as EasyPaisa.
- Raast P2M: SBP's instant payment QR — lowest cost, fastest growing.
- Bank transfer (manual reference).
- Store credit / wallet.
- Split payment (e.g., Rs. 1500 cash + Rs. 500 EasyPaisa).
- Per-tenant payment method enable/disable.

See `INTEGRATIONS.md` for protocol details on each.

### Phase 6 — Returns, refunds, customer ledger (week 11)

- Return against invoice (within FBR rules — credit note in FBR system).
- Partial returns.
- Refund to original payment method (or store credit).
- Customer ledger (purchases, returns, payments, balance).
- Customer groups and group-level pricing.

### Phase 7 — Reports & analytics (weeks 12–13)

- Daily sales summary (per terminal, per cashier, per branch).
- Item-wise sales (top sellers, slow movers).
- Category-wise sales.
- Tax report (FBR-format, ready for monthly return).
- Stock report (current levels, valuation).
- Profit & loss (uses purchase cost vs sale price).
- Cashier performance (sales/hour, average ticket).
- Payment-method breakdown.
- Returns analysis.
- Customer top-N.
- All reports exportable as Excel and PDF.
- Admin dashboard with charts (Recharts): revenue trend, top products, sync health, FBR submission health.

### Phase 8 — Polish, hardware, packaging (weeks 14–16)

- Cash drawer integration (RJ11 trigger via printer).
- Customer-facing display (second monitor, HTML page rendered by Electron).
- Weighing scale integration (serial/USB) for groceries — V1 supports manual weight entry, scale integration in V1.5.
- Animation polish: page transitions, success states, micro-interactions.
- Performance: every cashier interaction under 200ms, every screen load under 1s on a 4 GB RAM machine.
- Accessibility audit: keyboard navigation everywhere, focus rings, screen reader labels.
- Urdu localization for receipt templates and core POS strings.
- Electron installer signing (so Windows SmartScreen doesn't scare customers).
- Documentation: 5-minute video tutorials for cashier, manager, owner roles.
- Onboarding wizard: from "I just installed this" to "I made my first sale" in under 30 minutes.

**Exit criteria for V1 launch:** Three pilot shops running for two weeks with no critical bugs, daily syncs successful, FBR submissions all valid, cashiers happy.

---

## 7. Working with Claude Code in VS Code

Some practical patterns for getting maximum mileage out of Claude Code on this project:

**Plan in chat, build in code.** Use the chat panel to think through architecture decisions, edge cases, and SQL schemas. Use inline tools (`@file`, agent edits) to actually write code. Don't expect Claude to remember context across sessions — re-share the relevant `.md` file at the start of each work session.

**One Claude task per phase, not per project.** When you start phase 2, open a fresh chat and paste in `PROJECT_PLAN.md` + the relevant phase section + `DATABASE_SCHEMA.md`. Don't try to make Claude carry the entire project context — it'll lose details.

**Test-driven for tax-critical paths.** For anything touching FBR submission, taxes, cancel-budget, or money: write the test first, in chat, with explicit expected inputs and outputs. Then ask Claude to implement against those tests. This is the path to fewest bugs in the parts that matter most.

**Two-PR workflow for risky changes.** First PR: Claude writes the change with tests. Second PR (after review): you tighten edge cases. Don't merge huge Claude-generated changes without reading them.

**Use feature branches, never push to main.** Every change goes through a PR even if it's solo development. CI catches regressions.

**Recommended VS Code extensions to pair with Claude Code:**

- ESLint + Prettier (auto-format on save).
- Error Lens (inline error highlighting).
- GitLens (commit history at a glance).
- Thunder Client (test API endpoints without leaving editor).
- SQLTools + Postgres driver (query DB during dev).

**Code review checklist when Claude generates a change:**

1. Are all monetary values stored as `Decimal` (Python) or integer paisa (everywhere else)? Never `float`.
2. Is every API endpoint protected by the right permission?
3. Does every database write go through a transaction?
4. Is every external call (PRAL, payment gateway) wrapped in retry with timeout?
5. Are there tests for the unhappy path, not just the happy path?
6. Does the code log enough to debug a production issue without being chatty?

---

## 8. Hosting & deployment

### Single-VPS layout for V1

Specs to start: **4 vCPU, 8 GB RAM, 200 GB SSD** (~$10/month on Contabo or Hetzner). Comfortably handles ~500 customer shops with the workload we'll generate.

Process layout on the box (managed by systemd):

| Service | Memory | Notes |
|---|---|---|
| Nginx | 50 MB | TLS termination, static files, rate limiting |
| Gunicorn (Django) | 4 × 200 MB = 800 MB | 4 workers, async via `gthread` |
| Celery worker (default) | 2 × 250 MB = 500 MB | sync, reports |
| Celery worker (FBR) | 2 × 250 MB = 500 MB | dedicated queue, no head-of-line blocking on big reports |
| Celery beat | 100 MB | scheduled jobs |
| PostgreSQL | 2 GB | tuned `shared_buffers = 1GB` |
| Redis | 200 MB | maxmemory 200mb, allkeys-lru |
| Glitchtip (error tracking) | 500 MB | optional, can be deferred |

Total ~5 GB used, leaves plenty of headroom.

### Static IP requirement

PRAL whitelists 1–3 outbound IPs. Confirm with your VPS provider that you can pin an IP (most do by default). When changing servers, plan a 4-hour PRAL re-whitelisting window.

### Deployment

`git push` to a `main` branch triggers GitHub Actions which:

1. Runs tests.
2. Builds Docker images.
3. SSHs to the VPS, pulls images, runs migrations, restarts services with zero-downtime via systemd's `start-or-restart` and Gunicorn's graceful reload.

For database migrations that take more than 1 second: use a separate maintenance window. Postgres locks bite on large tables.

### Backups

- **Postgres**: nightly logical dump (`pg_dump`) compressed and uploaded to Backblaze B2. Retain 30 daily, 12 monthly, 5 yearly.
- **POS terminal SQLite**: copied to user's `Documents/POS/backups/` daily, plus uploaded to our cloud weekly (only if customer has internet that day).
- **Restore drill**: every 3 months, restore the previous night's backup to a staging server and verify integrity. If you've never restored a backup, you don't have backups.

### Monitoring

- **Uptime**: UptimeRobot free tier pings the API every 5 minutes.
- **Errors**: Glitchtip self-hosted (free) or Sentry free tier (5000 events/month).
- **Logs**: Loki + Grafana, or just `journalctl` for V1. Don't over-engineer.
- **Metrics**: Postgres slow query log + a weekly review session.

---

## 9. Cost breakdown

For the FIRST 100 paying customer shops:

| Item | Monthly | Annual |
|---|---|---|
| VPS (Contabo 4 vCPU / 8 GB) | $10 | $120 |
| Backups (Backblaze B2, ~50 GB) | $0.25 | $3 |
| Domain + DNS (Cloudflare) | $1 | $12 |
| Email (Brevo free tier) | $0 | $0 |
| SMS (~5000 SMS/month @ Rs. 0.50) | ~$10 | ~$120 |
| Error tracking (Glitchtip self-hosted) | $0 | $0 |
| Code signing certificate (annual, for Electron) | — | $80 |
| Total fixed cloud cost | ~$22 | ~$335 |

At Rs. 5000/month per shop subscription × 100 shops = Rs. 500,000/month gross. Cloud cost = Rs. 6,000/month. Margin is dominated by support and sales, not infra. **The architecture is correct.**

If you grow past 500 shops: add a Hetzner CCX22 ($30/month) as a Postgres replica, move backups to a second region. Past 2000 shops: dedicated DB server, app servers behind a load balancer. None of this is needed for V1.

---

## 10. Security & compliance checklist

### Application security

- [ ] All passwords hashed with Argon2id (Django default is PBKDF2 — override).
- [ ] JWT access tokens 15 minutes, refresh tokens 7 days, rotation on use.
- [ ] Role-based permissions enforced in serializers AND in queryset filters.
- [ ] CSRF protection on session endpoints, tokens elsewhere.
- [ ] Rate limiting on auth endpoints (5 attempts / 15 min / IP).
- [ ] All external API calls have explicit timeouts (no infinite waits).
- [ ] Idempotency keys on all sync POSTs.
- [ ] SQL injection: only ORM, never string interpolation.
- [ ] XSS: React escapes by default; never use `dangerouslySetInnerHTML`.

### Tax & audit compliance

- [ ] Six-year retention for all invoices, returns, payments, FBR submission logs.
- [ ] Audit log is append-only, includes user, timestamp, IP, action, before/after JSON.
- [ ] Invoice numbers monotonically increase per terminal per day; gaps are anomalies and flagged.
- [ ] FBR Invoice Number is the source of truth once received; never modified locally.
- [ ] 72-hour edit window enforced server-side, not just UI.
- [ ] 10% monthly cancel cap enforced server-side, with running counter visible to user.
- [ ] All money stored as Decimal (Python) or integer paisa (JS); no floats.

### Data security

- [ ] Database encrypted at rest (Postgres on encrypted filesystem).
- [ ] Backups encrypted before upload (gpg with passphrase from secrets manager).
- [ ] FBR tokens, payment gateway secrets stored in environment variables, never in code, never in DB plain text.
- [ ] Per-tenant data isolation enforced at the queryset level (every queryset filters by `tenant_id`).
- [ ] PII (CNIC, phone) stored only when needed; minimize collection.

### Operational

- [ ] SSH key-only access to production server (no passwords).
- [ ] Fail2ban on SSH and HTTP auth endpoints.
- [ ] Automatic security patches (`unattended-upgrades`).
- [ ] Off-server backups (Backblaze B2 in a different region from VPS).
- [ ] Quarterly restore drill.
- [ ] Incident runbook checked into the repo.

---

## 11. Risks & mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| FBR API changes mid-flight | High | High | Subscribe to PRAL CRM updates; keep the JSON builder isolated in one module; integration tests against sandbox run nightly |
| PRAL sandbox down during onboarding | Medium | Medium | Cache scenario test results; allow customer to register but not yet test until sandbox returns |
| Customer's internet down for >72 hours | Low | High | Document the manual amendment-via-IRIS escape hatch; alert customer when invoices are aging toward expiry |
| Cancel budget exhausted mid-month | Medium | Medium | UI clearly shows remaining; teach cashiers to use credit notes; admin can be alerted at 80% consumption |
| Receipt printer jam during sale | Medium | Low | Sale completes regardless; reprint button available; printer error is logged |
| POS terminal disk failure | Low | High | Daily local backup to USB; weekly cloud backup; recovery procedure documented |
| Pirated copies of our software | Medium | Medium | License-key activation, online verification heartbeat (degrades to read-only after 30 days offline) |
| Cashier theft via void/edit abuse | Medium | High | Voids require manager PIN above Rs. X threshold; daily audit report flags unusual patterns |
| Pakistani rupee depreciation breaks fixed-rate pricing | High | Low | Subscription denominated in PKR, reviewed annually |
| Competitor matches feature parity | High | Low | Focus on superior support + onboarding speed; technology is not the moat |
| FBR mandates additional integration we haven't built | High | High | Allocate 20% buffer in roadmap for compliance changes; modular FBR module makes adding features cheaper |

---

## 12. Success metrics for V1

If we hit these in the first 6 months post-launch, V1 is a success:

- **Reliability**: 99.5% uptime for the central server. Less than 1 sync failure per 10,000 invoices.
- **Performance**: 95th percentile cashier interaction <300ms locally; 95th percentile FBR submission <5s.
- **Compliance**: Zero invoices with incorrect FBR data; cancel-budget violations caught at UI before reaching server.
- **Onboarding**: Median time from purchase to first sale <60 minutes.
- **Support**: Median support ticket resolution <8 hours.
- **Sales**: 50 paying customers in first 6 months. (Adjust based on your sales channel.)

---

## 13. What's deliberately deferred to V2

Don't try to ship these in V1. They will distract you and delay launch.

- Mobile app (React Native or Flutter) for owners checking sales on the go.
- Multi-currency support.
- Advanced loyalty programs (points, tiers, rewards).
- E-commerce integration (Shopify, Daraz).
- ~~Restaurant-specific features (table management, kitchen display, course timing).~~ **SHIPPED** as the `restaurant` vertical: order types (dine-in/takeaway/delivery), tables + floor map, menu modifiers, KOT thermal printing + send-to-kitchen, on-screen kitchen display (KDS), and split payment. Gated by `Tenant.vertical == "restaurant"` + the `restaurant` module so grocery/pharmacy/DI are untouched. See `apps/restaurant/`.
- Salon/service business workflows (appointments, technician commission).
- Wholesale-specific features (price tiers, credit terms, bulk pricing).
- Provincial sales tax (SRB Sindh, PRA Punjab) — federal FBR first; provinces in V2.
- AI-driven recommendations, fraud detection, demand forecasting.
- White-label for resellers.

Pick ONE of these as your V2 differentiator after V1 stabilizes. Don't do all.

---

## 14. Glossary

- **POS** — Point of sale; the terminal where the cashier rings up sales.
- **PRAL** — Pakistan Revenue Automation (Pvt.) Ltd., the company FBR uses to operate the digital invoicing platform.
- **FBR** — Federal Board of Revenue, Pakistan's federal tax authority.
- **IRIS** — FBR's taxpayer-facing portal (not to be confused with iris the eye thing).
- **IRN** — Invoice Reference Number; the unique ID FBR returns for each validated invoice.
- **Tier-1 Retailer** — A category of large retailer subject to additional reporting; defined in the Sales Tax Act.
- **STRN** — Sales Tax Registration Number.
- **NTN** — National Tax Number.
- **HS Code** — Harmonized System Code; international product classification for tax purposes.
- **SRO** — Statutory Regulatory Order; an FBR regulation.
- **SDC** — Sales Data Controller; older Tier-1 POS reporting middleware.
- **Annexure-C** — A specific tax return form referenced by PRAL's invoice cancellation rules.
- **PSEB** — Pakistan Software Export Board; required registration for licensed integrators.

---

*Last updated: see git log. This document is the contract; if you change the plan, update this file in the same PR.*
