# Claude Code prompts — phase by phase

> Copy each prompt verbatim into a fresh Claude Code session after running `/clear`. Always engage Plan Mode (`Shift+Tab` twice) before sending. Always create a feature branch before starting.

## How to use this file

For each phase:

1. In VS Code's integrated terminal: `git checkout main && git pull && git checkout -b phase-N-shortname`
2. Open a new Claude Code chat (Spark icon → new conversation, or `/clear` an existing one).
3. Press `Shift+Tab` twice to enable Plan Mode.
4. Paste the phase's prompt.
5. Read Claude's plan critically. Push back on anything that doesn't match the four design docs.
6. Iterate the plan until it's right. Then approve.
7. Review every diff Claude produces. Don't auto-accept on tax/money/FBR-related code.
8. When the phase is complete: run verification, commit in logical chunks, push, open PR, merge after self-review.
9. `/clear` and start the next phase.

The prompts deliberately reference specific sections of the docs rather than restating their contents. Claude reads the files; you don't have to paste them.

---

## Phase 0 — Foundation (week 1)

**Goal**: monorepo + Django backend + admin web shell + POS terminal shell, all running locally via docker-compose, all wired to a single Postgres. By the end of this phase, you can register a tenant, log into admin, and open the POS app — all three see the same database.

**Branch**: `phase-0-foundation`

**Prompt**:

```
Read PROJECT_PLAN.md sections 5 and 6, DATABASE_SCHEMA.md sections 1 and 2,
INTEGRATIONS.md section 4, and CLAUDE.md.

We are starting Phase 0 of the roadmap. The repo is currently spec-only —
no code, no scaffolding. Your job is to produce the foundation.

Goal: a monorepo with three runnable applications, all sharing one Postgres
database, all started by a single docker-compose command. By the end of this
phase I should be able to:

  - run `docker compose up` and have Postgres + Redis + Django serving on
    localhost
  - run the admin web app in dev mode and see a login screen
  - run the POS terminal in dev mode and see its login screen
  - register a tenant via the Django admin
  - log in to the admin web app as that tenant's owner
  - log in to the POS terminal with a cashier PIN

Before writing any code, produce a plan covering:

1. The exact directory structure under the repo root, matching the layout
   in PROJECT_PLAN.md section 5. Include every folder you'll create and
   every top-level config file.

2. Pinned versions for all major dependencies:
   - Python (3.12), Django (5.x LTS), Django REST Framework
   - djangorestframework-simplejwt for JWT
   - argon2-cffi for password hashing
   - psycopg (v3, not psycopg2)
   - celery, redis-py
   - Node, Vite, React, TypeScript, Tailwind, shadcn/ui, Zustand,
     TanStack Query, Lucide
   - Electron, electron-builder, better-sqlite3
   - All dev dependencies: pytest, pytest-django, ruff, mypy, eslint,
     prettier

3. The docker-compose.yml services: Postgres 16, Redis 7, Django web
   (with hot reload), Celery worker, Celery beat. Each with named volumes,
   health checks, and a shared network. No managed services.

4. Django settings layout: core/settings/base.py, dev.py, prod.py, test.py.
   What goes where. Environment variable handling via django-environ or
   pydantic-settings — pick one and justify.

5. Multi-tenancy approach: row-level via tenant_id FK on every model,
   enforced by a base manager class TenantScopedManager that filters every
   queryset by request.tenant. Show me the manager + middleware design,
   not just the description.

6. Argon2id password hashing override (Django defaults to PBKDF2). The
   exact PASSWORD_HASHERS setting and any tuning parameters.

7. JWT auth setup: access tokens 15 minutes, refresh tokens 7 days,
   refresh rotation on use, blacklist enabled. Token payload should
   include user_id, tenant_id, role.

8. The Django apps to create in this phase: accounts, tenants. The exact
   models for tenants.Tenant, accounts.User, tenants.TenantMembership,
   with field-by-field mapping to DATABASE_SCHEMA.md section 1 SQL.
   Note any places where Django ORM forces a slight deviation from the
   raw SQL — explain each deviation.

9. Initial migration commands and the order they run.

10. The admin web shell: Vite + React + TypeScript + Tailwind + shadcn/ui
    initialized, login route with form (no real auth wiring yet beyond
    JWT POST), protected-routes hook, App shell with sidebar layout per
    SCREENS.md Part C "Universal admin chrome".

11. The POS terminal shell: Electron + React + TypeScript + Tailwind +
    better-sqlite3 initialized, splash → login (PIN keypad per SCREENS.md
    section A1), and the SQLite schema file from DATABASE_SCHEMA.md
    section 10 (the outbound_queue table only — full SQLite schema comes
    in Phase 1+).

12. Shared types folder: which types belong here in Phase 0. Probably
    just User, Tenant, TenantMembership, AuthResponse.

13. CI: a single GitHub Actions workflow that runs on PR — lint and
    typecheck for all three apps, pytest for backend. No deploy yet.

14. README.md at repo root: how to clone, install, run, and what the
    three apps are. Concise.

15. .env.example files for backend, admin-web, pos-terminal showing every
    environment variable needed without real values.

16. Verification steps I'll run after you implement, in order, with the
    exact expected output for each:
    - docker compose up
    - python manage.py migrate
    - python manage.py createsuperuser, then create a Tenant in admin
    - npm run dev in admin-web → log in, see empty dashboard
    - npm run dev in pos-terminal → log in with cashier PIN, see empty
      sale screen

Constraints:

- Do NOT scaffold any feature beyond what Phase 0 requires. No catalog,
  no sales, no FBR. Just identity + tenancy + the three runnable shells.
- Every model in the DB has tenant_id NOT NULL, except User (which can
  belong to multiple tenants via TenantMembership) and global lookups
  (none in Phase 0).
- Money fields, when introduced, must be DECIMAL(14, 4). None are needed
  yet but configure the convention.
- Use UUID v7 primary keys via a small helper. Document where the helper
  lives.
- Every model has created_at and updated_at managed automatically.
- audit_log will be created in a later phase, but reserve the spot in
  the migration order.

Do not write any files yet. Show me the plan first. I will review section
by section. After approval, implement. After implementation, give me the
exact commands to run for each verification step in order.
```

**Approval checklist** (read Claude's plan against these before approving):

- [ ] Directory layout matches `PROJECT_PLAN.md` section 5 exactly.
- [ ] No managed services (no AWS, no SaaS) snuck in.
- [ ] Argon2id is the default password hasher, not just available.
- [ ] JWT lifetimes are 15m / 7d, not Django/SimpleJWT defaults.
- [ ] `TenantScopedManager` is the default manager on every tenant-scoped model.
- [ ] Tenant filtering is enforced in middleware, not just relied on at the view layer.
- [ ] The three shells are runnable independently — no cross-app build dependency.
- [ ] No code is written before you say "approved".

**After implementation, verify**:

```bash
# from repo root
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
# → log into Django admin, create a Tenant, create a TenantMembership

cd admin-web && npm run dev
# → log in as the user, land on empty dashboard

cd ../pos-terminal && npm run dev
# → log in with cashier PIN, land on empty sale screen
```

**Commit message convention**: `phase-0: initial scaffolding — backend, admin, pos, docker`

---

## Phase 1 — Catalog & inventory (weeks 2–3)

**Goal**: products, categories, units, HS codes, tax rates; stock levels per branch; stock movements as an append-only ledger; CSV import. The POS can browse the catalog offline.

**Branch**: `phase-1-catalog`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 1 only), DATABASE_SCHEMA.md sections
3, 4, and 5, SCREENS.md Part C sections A5 and A6, and CLAUDE.md.

Phase 0 is complete. We have identity, tenancy, and three runnable shells.
Now we are building Phase 1: catalog and inventory.

Goal: a complete catalog and inventory system. By the end of this phase I
should be able to:

  - import a 500-row product CSV via admin web
  - see those products in the admin web with pagination, search, and
    filtering
  - see them in the POS terminal product grid (offline)
  - adjust stock levels manually with reasons, see the audit ledger
  - transfer stock between two branches
  - run a physical count audit, finalize it, see resulting adjustments
  - get low-stock email alerts at the tenant's configured threshold

Before writing any code, produce a plan covering:

1. The Django apps to create or extend: catalog, inventory. Each app's
   models, migrations, serializers, viewsets, and URL routing.

2. Field-by-field mapping from DATABASE_SCHEMA.md section 3 to Django
   models for: UnitOfMeasure, HsCode, TaxRate, Category, Product,
   ProductVariant, ProductBatch. Note where Django's defaults override
   the spec (e.g., UUID PKs, timestamp triggers).

3. Same mapping for DATABASE_SCHEMA.md section 4: StockLevel,
   StockMovement (append-only — show me how you enforce this), 
   StockTransfer + items, StockAudit + items.

4. Seed data approach:
   - units_of_measure: ~20 entries (PCS, KG, GM, LTR, ML, BOX, DOZEN,
     PACK, METER, etc.). Include name_ur for each.
   - hs_codes: source from FBR's published list. Show me the import
     script. Don't bundle 5000 rows in a migration; provide a management
     command that fetches and seeds.

5. The CSV import flow:
   - column mapping wizard (UI)
   - server-side validation (every row, every column)
   - dry-run preview (count of new, updated, errored)
   - commit step with bulk_create / bulk_update for performance
   - error report download
   Specify the exact format and column headers we'll accept.

6. The admin web screens, per SCREENS.md A5 and A6:
   - Products list (table with filters, bulk actions)
   - Product create/edit (sectioned form per A6.2)
   - Categories tree (drag-to-reparent — pick a library or build it)
   - Tax rates list + edit
   - HS code browser (read-only, searchable)
   - Stock by branch table
   - Stock movements ledger
   - Stock adjustments wizard
   - Stock transfers (initiate + receive)
   - Stock audits

7. The POS terminal changes:
   - SQLite schema additions: products, categories, stock_levels mirror
     tables (read-only on POS, synced from server)
   - Initial sync on first login: pull catalog from server
   - Periodic sync: poll for catalog changes
   - Local search index over products (FTS5 on SQLite)
   - Product grid component on the main sale screen (not yet wired to
     cart — that's Phase 2)

8. Background jobs (Celery):
   - daily low-stock digest email at 7am tenant-local
   - weekly stock valuation report cached in Redis

9. Permissions: who can do what, mapped to roles_permissions matrix in
   DATABASE_SCHEMA.md section 1. Specifically:
   - Cashier: read-only on catalog
   - Manager: full CRUD on catalog and inventory in their branches
   - Owner: full CRUD across all branches
   - Accountant: read-only

10. Tests:
    - unit tests for every model (validation, save hooks)
    - API tests for every endpoint (success, validation errors,
      permission denied across tenants)
    - integration test: CSV import 100 rows end-to-end
    - integration test: stock transfer with variance reconciliation

11. Verification steps I'll run after implementation:
    - run migrations, see new tables in Postgres
    - via Django admin, create 2 branches and 1 category
    - via admin web, import the sample CSV (provide a 50-row sample)
    - via admin web, set stock levels for 5 products
    - via POS, log in offline (disconnect network), see those products
      and stock counts
    - via admin web, transfer 3 of one product from branch A to branch B,
      see the in-transit state, receive at B with variance, see
      reconciliation

Constraints:

- Every product, category, tax rate, customer (etc.) is tenant-scoped.
  TenantScopedManager from Phase 0 enforces this. Verify in tests.
- stock_movements is APPEND-ONLY. UPDATE and DELETE on this table are
  REVOKEd at the database level. Show me the migration SQL.
- Money is DECIMAL(14, 4) on every Python model field. Quantity is
  DECIMAL(14, 4) too (we sell 1.5 kg of rice).
- POS-side SQLite schema mirrors only the fields the cashier needs.
  Don't replicate cost_price to the POS — cost is owner-confidential.
- HS code search must be fast — full-text index on description.
- The CSV import handles UTF-8 BOM, Windows line endings, and quoted
  fields with commas. Test for these.

Do not write any files yet. Show me the plan. After approval, implement
and provide verification steps in order.
```

**Approval checklist**:

- [ ] `stock_movements` immutability is enforced at the DB level (REVOKE), not just by convention.
- [ ] HS code seed is a management command, not bundled in a migration.
- [ ] CSV import has a dry-run before commit.
- [ ] POS-side SQLite does NOT store `cost_price`.
- [ ] Permission tests cover cross-tenant access (user from tenant A cannot read tenant B's products).
- [ ] Categories support nesting (parent/child) and drag-reparent.
- [ ] FTS index on products and HS codes.

---

## Phase 2 — Sales & cash payments (weeks 4–5)

**Goal**: the cashier can ring up a sale, take cash, print a receipt, open the drawer. Local SQLite captures everything; sync to server is stubbed (real sync comes in Phase 3).

**Branch**: `phase-2-sales`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 2), DATABASE_SCHEMA.md section 7
(focusing on invoices, sale_items, payments — defer FBR fields for now
but include the columns), SCREENS.md Part A sections 1 through 12 and
14, INTEGRATIONS.md sections 2.1 and 3.1 and 3.2 and 3.3, and CLAUDE.md.

Phases 0 and 1 are complete. We have identity, tenancy, three runnable
shells, and a fully working catalog + inventory. Now Phase 2: sales and
cash payments end-to-end on the POS terminal.

Goal: a cashier can complete a real sale offline. By the end of this
phase I should be able to:

  - log in to the POS, open the day with a cash float
  - scan or search products, add to cart, change quantities
  - apply line and cart discounts (with manager PIN above threshold)
  - hold a sale, ring up another, recall the held sale
  - select a customer (registered or walk-in)
  - take cash payment with change calculation
  - have the cash drawer open automatically
  - print a thermal receipt (80mm or 58mm)
  - see the sale in admin web's sales list (with sync stubbed for now —
    Phase 3 wires real sync)
  - close the day, reconcile cash, see variance

Before writing any code, produce a plan covering:

1. Django apps to create or extend: sales, customers. Models per
   DATABASE_SCHEMA.md section 6 (customers, customer_groups,
   customer_ledger) and section 7 (invoices, sale_items, sale_item_history,
   payments). Discounts table from section 7 too.

2. The local SQLite schema additions on POS terminal: invoices,
   sale_items, payments, customers (synced subset), held_sales (concept
   = invoices.is_held = TRUE). Plus the outbound_queue from Phase 0 for
   when sync is enabled.

3. Sale state machine on the POS:
   - empty → has_items → payment → success → empty
   - held branches: any state → held → recalled
   - Each transition: what data is written, what UI animation plays.

4. The product grid component (right side of main sale screen per
   SCREENS.md A3):
   - virtualized for 10,000+ products
   - debounced text search
   - barcode scanner integration (USB HID — keystrokes routed to the
     hidden search input when no modal is open; specify the focus
     management strategy)
   - quantity-prefix input (cashier types "3" then taps apple → adds 3)
   - long-press to set quantity

5. The cart component (middle of main sale):
   - line items with qty +/- buttons
   - tap to edit (modal per SCREENS.md A7)
   - swipe-left to delete with undo toast
   - cart-level discount with manager PIN gate
   - customer slot

6. Customer selection modal (SCREENS.md A5) and quick-add (A6):
   - phone/CNIC/name search against synced customer subset
   - "walk-in" pinned at top
   - new customer creation in 30 seconds, validated PK phone format

7. Held sales:
   - hold from cart → label → save to local SQLite with is_held=TRUE
   - recall list shows all held sales for this terminal
   - recalling replaces current cart (warn if non-empty)

8. Payment screen (SCREENS.md A10):
   - in Phase 2, ONLY cash is enabled. Other method buttons are visible
     but disabled with "available in Phase 5" tooltip
   - tendered/remaining display, animates on change
   - quick-pick chips: exact, 1000, 5000
   - change calculation
   - complete sale button enabled only when remaining ≤ 0

9. Sale success screen (A11):
   - large checkmark with stroke draw animation
   - local invoice number (FBR number is null until Phase 4)
   - print, email, SMS receipt buttons
   - new sale button
   - 5-second auto-advance (configurable)

10. Receipt printing (INTEGRATIONS.md section 3.1):
    - node-thermal-printer integration in Electron main process
    - 80mm (48 chars) and 58mm (32 chars) layouts
    - tenant header/footer from tenant_settings
    - logo printing as bitmap
    - QR code placeholder (real FBR QR comes in Phase 4)
    - reprint from sales history
    - graceful degradation if printer unavailable: toast "Receipt failed
      to print, sale completed regardless"

11. Cash drawer (INTEGRATIONS.md section 3.3):
    - triggered via the printer's drawer kick command
    - opens automatically on cash payment completion
    - "no-sale" button in cashier menu, opens drawer, logs to audit_log
      (audit_log model from Phase 0 stub — extend in this phase)

12. Day open / day close (SCREENS.md A2 and A14):
    - day open: opening cash float, denomination breakdown optional
    - day close wizard: 3 steps (summary, count, variance reason)
    - cash session row written to Postgres (synced) and SQLite (cached)
    - terminal locked between close and next open

13. Held sales recall list (SCREENS.md A9).

14. Admin web sales list (SCREENS.md A3.1) — basic version:
    - filters: date range, status, branch, terminal, cashier, customer
    - columns per spec
    - click → invoice detail (SCREENS.md A3.2) showing line items,
      payments, totals, audit trail

15. Audit log:
    - extend the audit_log model from Phase 0 stub
    - REVOKE UPDATE, DELETE on the table
    - log every: sale created, sale held, sale recalled, line edited,
      line removed, discount applied, no-sale event, day open, day close
    - include user_id, ip_address, before/after JSON

16. Sync stub:
    - the POS writes invoices to local SQLite immediately
    - it ALSO enqueues a row in outbound_queue for sync
    - in Phase 2, the sync worker is a no-op stub that logs "would
      sync invoice X" — real sync logic lands in Phase 3
    - admin web sales list is populated by manually inserting test
      invoices via Django shell for now

17. Money math:
    - all calculations in Python use Decimal with quantize(0.01)
    - all calculations in TypeScript on POS use a Money utility class
      backed by integer paisa
    - tax math: per-line round to 4 decimals, sum, then round display
      to 2 decimals
    - test that Rs 1000 × 18% = Rs 180.00 exactly, no float drift

18. Tests:
    - unit: Money utility, tax calculator, change calculator
    - integration: full sale flow on POS (mocked printer)
    - integration: hold + recall preserves all state
    - integration: day close variance computed correctly
    - cross-tenant: cashier from tenant A cannot see tenant B's invoices

19. Animations to implement (SCREENS.md Part E):
    - cart item add (spring scale)
    - total counter rolling
    - button press (0.97 scale)
    - success checkmark draw
    - card shake on wrong PIN
    - sale row swipe-to-delete with undo

20. Verification steps:
    - boot POS, day-open with Rs 5000 float
    - add 5 items via barcode scanner, modify qty on one
    - apply 10% discount on cart (no PIN needed)
    - apply 20% discount (PIN required, manager PIN works)
    - hold sale labeled "Ahmed", start new sale
    - recall Ahmed's sale, complete with cash Rs 2000
    - drawer opens, receipt prints with all line items, totals, QR
      placeholder
    - log in as walk-in customer, ring up Rs 350, complete
    - day-close, declare Rs 7350, see no variance
    - via admin web, see both sales in the list with statuses

Constraints:

- The POS works fully offline through this phase. Pulling the network
  cable mid-sale must not break anything. Test for this explicitly.
- Money never touches a float, on either side.
- Receipts are printed from the Electron main process, not the renderer.
- The drawer fires only on confirmed cash payment, never speculatively.
- Held sales are scoped per-terminal — terminal 1 cannot recall a sale
  held on terminal 2 in the same branch (they're physically different
  carts).
- Every modification to a sale (after creation) writes a sale_item_history
  row. Even though FBR rules don't apply yet, build the history table now.

Do not write any files yet. Show me the plan. After approval, implement
and provide verification steps in order.
```

**Approval checklist**:

- [ ] `audit_log` cannot be UPDATEd or DELETEd at the DB level.
- [ ] All money math goes through one utility, never raw Decimal/float scattered around.
- [ ] Printer failures don't block sale completion.
- [ ] Drawer trigger is only on confirmed cash payment.
- [ ] POS still works with the network cable pulled.
- [ ] Cross-tenant test exists for invoice access.
- [ ] Phase 4's FBR fields are present in the schema as nullable, not added later (avoid migration churn).

---

## Phase 3 — Sync engine (week 6)

**Goal**: the hardest phase. Make the POS a real local-first system. Everything written locally must reach the server reliably even through network failures, app crashes, and PRAL outages.

**Branch**: `phase-3-sync`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 3), DATABASE_SCHEMA.md section 10,
INTEGRATIONS.md section 4.1 (idempotency end-to-end), and CLAUDE.md.

Phases 0–2 are complete. Sales work end-to-end on the POS but only land
in local SQLite. The "sync" today is a no-op stub. This phase replaces
the stub with a real, robust sync engine.

Goal: every write that originates on the POS reaches the server exactly
once, in order, even through arbitrary network and process failures.

By the end of this phase I should be able to:

  - pull the network cable mid-sale, complete the sale, plug the cable
    back in 10 minutes later, and watch the sale appear in admin web
    without intervention
  - kill the POS process mid-sale (force quit), restart, finish the
    queued sync — no duplicate sale, no lost sale
  - have 50 invoices stacked in the queue from a 4-hour offline period
    drain in order when reconnected
  - see per-terminal sync health in admin web (green dot, amber syncing,
    red error)
  - manually retry a permanently-failed sync row from admin

Before writing any code, produce a plan covering:

1. The sync API on the Django side:
   - endpoint: POST /api/sync/invoices/, POST /api/sync/returns/, etc.
     One endpoint per entity type, or a generic one — pick one and
     justify.
   - idempotency: every request carries an Idempotency-Key header
     containing client_uuid. Server checks sync_log; if seen, returns
     the prior response without re-processing.
   - request schema: the entity payload + metadata (terminal_id,
     local_invoice_number, client_uuid, originating_timestamp).
   - response schema: server entity_id, server invoice_number (when
     applicable), validation errors (with line-level detail), retry
     hint.

2. The outbound queue worker on the POS:
   - polls outbound_queue WHERE status='pending' AND next_attempt_at <= now()
   - serial processing (one at a time, in insert order) — explain why
     not parallel
   - exponential backoff schedule: 10s, 30s, 2min, 10min, 1hr, 6hr,
     then permanent failure
   - jitter: ±20% randomization on backoff
   - max attempts: 5 (after which status='failed' permanently)
   - clean shutdown: finish current request before exit
   - resume on app start: any 'sent' status still present means the
     server didn't ack — re-send (idempotent so safe)

3. Failure mode handling:
   - network unreachable: backoff
   - DNS failure: backoff
   - 5xx from server: backoff
   - 4xx validation error: mark 'failed' immediately, do NOT retry,
     surface to admin
   - 4xx auth error: stop the queue worker, prompt re-login
   - timeout (>30s): backoff
   - connection reset mid-write: re-send (idempotent)

4. Conflict resolution:
   - sales: NEVER conflict. Every sale is a new row. The client_uuid
     ensures de-duplication.
   - inventory adjustments: last-write-wins, but sync_log retains all
     attempts so audit is preserved.
   - customer updates: last-write-wins on the field level (merge), with
     conflict logged.
   - product updates: server-wins (admin is source of truth for catalog).

5. Sync status indicator on the POS:
   - small dot in the header corner
   - green: queue empty, last sync < 60s ago
   - amber: queue non-empty, syncing in progress
   - red: queue has 'failed' rows OR last successful sync > 5 minutes
     and there are pending rows
   - tap to expand: list pending count, failed count, last successful
     sync time, manual "sync now" button

6. Admin web changes:
   - Dashboard tile: per-terminal sync health (online, last seen,
     pending count, failed count). Mirrors SCREENS.md A2.
   - Per-terminal detail page (SCREENS.md A14.2) showing recent sync
     events, manual force-resync button, manual retry on failed row.

7. Server-side sync log:
   - sync_log table from DATABASE_SCHEMA.md section 10 — implement now
   - every received request appended (even idempotent duplicates,
     marked status='duplicate')
   - retention: 90 days then auto-purge

8. Error reporting:
   - any 'failed' row triggers an in-app notification to the tenant
     admin (notifications table from section 11)
   - if 5+ rows fail within an hour, fire an email alert
   - failed rows surface as a banner in admin web

9. Concurrency:
   - terminal A and terminal B both syncing simultaneously is fine
     (different client_uuids, different rows)
   - same terminal sending the same client_uuid twice (network retry)
     hits idempotency check, returns prior response
   - clock skew between terminal and server is tolerated up to 1 hour;
     beyond that, log a warning

10. Tests:
    - unit: backoff schedule produces expected delays
    - unit: idempotency check returns prior response on duplicate
    - integration: simulated network failure mid-request, recovery on
      retry
    - integration: 100 invoices queued offline, all sync in order on
      reconnect
    - integration: app crash mid-sync, restart drains queue without
      dupes
    - chaos test: random 30% of requests fail, eventually all reach
      server exactly once
    - cross-tenant: terminal from tenant A cannot inject into tenant B
      (auth + tenant_id check)

11. Verification:
    - day-open POS, complete 5 sales online, watch each appear in admin
      within seconds
    - disconnect network (turn off Wi-Fi), complete 5 more sales
    - reconnect, all 5 appear in order within 30 seconds
    - kill POS process during a sync, restart, no duplicate, no loss
    - manually corrupt one queue row's payload (invalid product), see
      it transition to 'failed', see the admin notification, manually
      retry after fixing — succeeds
    - chaos: hit the server with 50 simultaneous sync requests from a
      load-test script, no race conditions

Constraints:

- The terminal NEVER blocks the cashier on sync. The queue is fully
  asynchronous from the sale flow.
- Idempotency is enforced via DB unique constraint on sync_log.client_uuid,
  not just application logic. Show me the migration.
- Backoff timer state lives in SQLite (next_attempt_at column) so it
  survives restarts.
- Serial processing on the terminal side prevents ordering issues.
  Document why; don't accidentally make it parallel for "speed".
- The queue worker process is separate from the UI thread. Crashes in
  one don't kill the other. Use Electron's utility process or a worker
  thread.
- Sync requests carry a JWT — the same one the cashier logged in with,
  refreshed automatically when expired.

Do not write any files yet. Show me the plan. This is the highest-risk
phase technically — I want to see your reasoning, not just code.
```

**Approval checklist**:

- [ ] Idempotency uses DB constraint, not application-level check.
- [ ] Backoff state survives process restart (in SQLite, not memory).
- [ ] Queue worker is in a separate process/thread from UI.
- [ ] Serial processing is justified, not just defaulted to.
- [ ] Conflict resolution is explicit per entity type.
- [ ] Chaos test is included, not just happy path.
- [ ] Failed rows surface to admin via notifications + email at threshold.

---

## Phase 4 — FBR integration (weeks 7–9)

**Goal**: real PRAL integration. Sandbox onboarding, scenario tests, production cutover, live submissions, edit/cancel rules, the 10% budget, the QR receipt.

**Branch**: `phase-4-fbr`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 4), DATABASE_SCHEMA.md section 9,
SCREENS.md Part C section A12, INTEGRATIONS.md Part 1 in full, and
CLAUDE.md.

Phases 0–3 are complete. Sales sync reliably to the server. Now we
integrate with PRAL/FBR to make the system tax-compliant.

Goal: a tenant can onboard with PRAL via our admin wizard, run sandbox
scenario tests, get production access, and have every sale submitted to
FBR in real time with full edit/cancel compliance.

By the end of this phase I should be able to:

  - register a fresh tenant for FBR via the admin wizard
  - declare our static IPs to PRAL on their behalf
  - run all eligible sandbox scenarios for the tenant's sector and see
    them all green
  - flip to production with the production token
  - complete a sale on POS, see it submitted to PRAL within 30 seconds,
    receive an FBR Invoice Number, print a receipt with QR code
  - within 72 hours, edit one item on a sale (per PRAL rules)
  - cancel a sale (within 72h, within budget), see the 10% budget tick
    down
  - exhaust the 10% budget, see the system block further cancellations
    and prompt for credit notes instead
  - on month rollover, see a new budget calculated from last month's sales

Before writing any code, produce a plan covering:

1. The Django app: fbr. Models from DATABASE_SCHEMA.md section 9 in full:
   FbrToken, FbrSubmission, FbrScenarioTest, FbrCancelBudget,
   FbrCancelBudgetConsumption, FbrIpWhitelist.

2. Token storage:
   - encrypt token_encrypted field with Fernet
   - encryption key from environment, never DB
   - a custom EncryptedTextField that handles encrypt-on-save,
     decrypt-on-load
   - test: tokens dumped via pg_dump are unreadable

3. JSON builder (INTEGRATIONS.md section 1.4):
   - module: backend/apps/fbr/builder.py
   - input: an Invoice + its SaleItems
   - output: the exact JSON shape PRAL expects
   - handle the gotchas: rate as "18%" string, uoM as verbose enum,
     buyerNTNCNIC as 13 zeros for unregistered, scenarioId only in
     sandbox
   - 100% test coverage on the builder. Every field, every variation.

4. PRAL client:
   - module: backend/apps/fbr/client.py
   - one class FbrClient with methods: post_invoice, validate_invoice,
     edit_invoice, cancel_invoice
   - all calls have 30s hard timeout
   - all calls log to fbr_submissions table (raw request + response)
   - retry only on transient errors (network, 5xx); never on 4xx
     validation errors
   - distinguish four error categories per INTEGRATIONS.md section 1.13

5. The onboarding wizard (SCREENS.md A12.1):
   - 6 steps as specified
   - step 5 (IP whitelisting): we submit OUR static IPs to PRAL — not
     the tenant's. Document where these IPs are configured.
   - step 6 (sandbox token): the tenant pastes a token from IRIS into
     our form; we encrypt and store
   - validation at each step before allowing next

6. Sandbox scenario testing:
   - module: backend/apps/fbr/scenarios.py
   - a registry pattern: @register("SN001") decorator on a builder
     function for each scenario
   - each builder takes the tenant context and returns a synthetic
     invoice JSON
   - support for SN001 through SN015+ (start with the ones the v1.6
     manual lists; design for easy addition)
   - admin UI: cards per applicable scenario (SCREENS.md A12.2),
     "run all" button, success/failure status, error details on click
   - production token activation: locked until all eligible scenarios
     pass

7. Real-time submission flow (INTEGRATIONS.md section 1.8):
   - on receipt of a sync'd invoice from POS, server enqueues a Celery
     task `submit_invoice_to_fbr(invoice_id)`
   - task posts to PRAL, persists response, updates invoice status
   - retry with exponential backoff per Phase 3 patterns
   - max 5 attempts before status='failed' and notification to admin
   - POS polls /api/invoices/{id}/status every 30s for pending invoices,
     updates local SQLite when status changes
   - on status='valid', POS reprints receipt with FBR QR (or prints for
     the first time if tenant chose "wait for FBR")

8. The 72-hour edit window:
   - set invoices.edit_deadline_at on transition to 'valid'
   - formula: MIN(submitted_at + 72h, last_day_of_current_month + 23:59:59)
   - all timezone math in PKT
   - Celery beat job hourly: transition to 'finalized' for invoices past
     edit_deadline_at
   - both UI and server-side enforce the deadline; UI is just for UX

9. The 10% monthly cancel cap (INTEGRATIONS.md section 1.10):
   - Celery beat job at 00:05 on the 1st of each month, in PKT:
     compute previous_month_sales per tenant, create new
     fbr_cancel_budget row, budget_amount = sales × 0.10
   - synchronous consume_cancel_budget function with
     SELECT...FOR UPDATE for atomic decrement
   - budget exceeded → raise CancelBudgetExceeded, surface clean error
   - admin web tracker (SCREENS.md A12.5): visual progress bar,
     consumption history, alerts at 80%

10. Edit/cancel constraint matrix (INTEGRATIONS.md section 1.11):
    - module: backend/apps/fbr/rules.py
    - predicate functions: can_edit_item, can_cancel_item,
      can_cancel_invoice
    - return (allowed: bool, reason: str | None)
    - called from both admin views and POS-initiated edits
    - test every path including the edge where one item edited makes
      the whole invoice uncancellable

11. QR code on receipts:
    - generate QR server-side using qrcode lib, return base64 PNG
    - store in invoices.fbr_qr_payload (the encoded data) and a derived
      image
    - POS receives it on status update, prints via ESC/POS image command
    - update receipt template to include QR + FBR invoice number

12. Failure handling and the manual amendment escape hatch:
    - if an invoice misses the 72h window (ours or PRAL's), the
      "manual amendment" admin panel (SCREENS.md A12.6) walks the user
      through doing it directly in IRIS
    - we provide guidance, copy-able invoice details, but don't
      automate (out of scope for V1)

13. The error-code mapping table:
    - module: backend/apps/fbr/error_mapping.py
    - dict of PRAL error codes → category (transient | validation |
      business | auth) + human-readable message
    - seed with codes from the v1.6 manual; designed for additions

14. Tests:
    - unit: builder produces valid JSON for every scenario
    - unit: rules predicates return correct results for every edge
    - integration: full flow against PRAL sandbox (gated behind a flag
      so CI doesn't burn sandbox quotas)
    - integration: cancel-budget atomicity under concurrent attempts
    - integration: timezone correctness on edit-deadline math
    - chaos: PRAL returns malformed JSON, we don't crash
    - chaos: PRAL returns 200 with statusCode '01', we mark failed not
      valid

15. Verification:
    - via admin, register a fresh test tenant
    - run the wizard, paste a real sandbox token from IRIS
    - select "All Other Sectors" and run scenario tests, see all green
    - paste production token (from sandbox after passing all scenarios,
      per PRAL flow)
    - on POS, complete a Rs 1180 sale (Rs 1000 + 18% tax)
    - see status transition: pending_sync → submitted → valid in <30s
    - see FBR Invoice Number on receipt with QR code
    - within 72h, edit one item's quantity → see partially_edited status
    - try to cancel that invoice → blocked because an item was edited
    - cancel a different sale → 10% budget consumed; verify budget
      tracker
    - simulate exhausted budget; try another cancel → blocked with
      "use credit note" suggestion
    - simulate a PRAL outage (block the gateway IP); make 3 sales
      offline, restore connection, all 3 submit and validate

Constraints:

- ALL FBR traffic egresses through our static IPs. Never from a
  tenant's local terminal. Document where this is enforced (network
  layer + application layer).
- Tokens are encrypted at rest. Audit confirms.
- The 72h window math is in PKT, period. Test with a sale at 23:59
  PKT on the 30th of a month — does it correctly clamp to month-end?
- The 10% cap is a HARD limit at the DB level (SELECT FOR UPDATE).
  No race conditions allowed.
- Once an invoice has a fbr_invoice_number, that field is immutable
  forever. Add a database trigger or check constraint.
- The QR payload is whatever PRAL specifies (or, until they specify,
  a JSON of {invoiceNumber, validatedAt, amount, sellerNTN}). Document
  this clearly so we can swap when PRAL publishes spec.
- This phase introduces real money and real tax compliance. Test
  coverage on builder, rules, and budget must be 100%. No exceptions.

Do not write any files yet. Show me the plan. This is the most
compliance-critical phase. I will be slow and careful in review.
```

**Approval checklist**:

- [ ] Tokens encrypted at rest; verified by inspecting raw DB.
- [ ] All FBR egress goes through declared static IPs (not from POS terminals).
- [ ] Cancel-budget uses `SELECT FOR UPDATE`, not application-level lock.
- [ ] Edit-deadline math is timezone-aware (PKT), tested at month boundary.
- [ ] `fbr_invoice_number` is immutable post-validation (DB-enforced).
- [ ] Builder has 100% test coverage including the gotcha fields.
- [ ] Rules predicates cover every edge case in section 1.11.
- [ ] Sandbox tests are gated by a flag so CI doesn't hit PRAL.

---

## Phase 5 — Multi-payment methods (week 10)

**Goal**: card, EasyPaisa, JazzCash, Raast, bank transfer, store credit, cheque, split payment.

**Branch**: `phase-5-payments`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 5), DATABASE_SCHEMA.md section 7
(payments table — all method-specific fields), SCREENS.md Part A
section A10 sub-flows, INTEGRATIONS.md Part 2 in full, and CLAUDE.md.

Phases 0–4 are complete. Cash sales work end-to-end with full FBR
compliance. Now we add the rest of Pakistan's payment methods.

Goal: every payment method documented in INTEGRATIONS.md Part 2 is
selectable, with the right sub-flow, and recorded in the payments
table with method-specific fields.

By the end of this phase I should be able to:

  - take a credit card payment with manual reference entry
  - take an EasyPaisa payment via static merchant QR + reference number
  - take a JazzCash payment same way
  - take a Raast P2M payment
  - take a bank transfer payment
  - apply customer store credit
  - record a cheque with pending status, then mark cleared/bounced later
  - split one sale across cash + EasyPaisa
  - have all of these submitted correctly to FBR with the right
    payment method recorded
  - configure per-tenant which methods are enabled

Before writing any code, produce a plan covering:

1. Payment methods config:
   - tenant_settings extension: enabled_payment_methods array
   - per-method config: easypaisa_merchant_id, jazzcash_mid,
     raast_iban, etc.
   - admin UI: Settings → Payment methods page with toggles + config
     fields per method

2. The payment screen sub-flows (SCREENS.md A10):
   - cash: already done in Phase 2
   - card: input fields for last-4, auth code, RRN; validation
   - easypaisa: full-screen QR display (static or dynamic — V1 static),
     reference number entry
   - jazzcash: same shape as easypaisa
   - raast: QR display, reference entry; in V1.5 dynamic QR via bank
     aggregator, but build the abstraction now
   - bank transfer: bank picker, last-4, reference
   - store credit: shows customer's available credit, applies up to
     that amount; requires customer selected
   - cheque: cheque number, bank, date; status starts 'pending'
   - tendered list, split-tender support

3. Adapter pattern:
   - module: backend/apps/payments/adapters/
   - one file per provider: cash.py, card.py, easypaisa.py,
     jazzcash.py, raast.py, bank_transfer.py, store_credit.py,
     cheque.py
   - each adapter implements: validate_input, record_payment,
     refund (where applicable)
   - generic interface so adding NayaPay, SadaPay etc. in V2 is one
     file

4. Customer-facing display integration (Part B SCREENS.md):
   - when QR-based methods are picked, the QR shows on customer
     display in addition to / instead of cashier screen
   - amount and merchant name overlaid

5. Cheque clearance workflow:
   - admin web has a "Pending cheques" view
   - mark cleared → updates cheque_status, customer_ledger if applicable
   - mark bounced → flags customer (notes on customer profile),
     reverses the sale's payment status to 'partially_paid' or
     'unpaid', creates an exception case for owner attention

6. Store credit accrual:
   - on returns (Phase 6), refunding to store credit increments
     customers.store_credit
   - on use, decrements and writes a customer_ledger row
   - test: store credit can never go negative

7. Refund flows by method:
   - cash: cashier hands cash, system records reversal
   - card: cashier processes reversal on physical terminal, enters RRN
   - wallet (EasyPaisa/JazzCash): cashier processes reversal in
     merchant app, enters reference
   - Raast: same as wallet
   - bank: manual transfer initiated by owner, recorded later
   - store credit: increments customer.store_credit, no external action
   - These get fully wired in Phase 6 (returns); in this phase, just
     the payment record side.

8. FBR submission update:
   - the JSON builder from Phase 4 doesn't actually carry payment-method
     detail to PRAL (PRAL only cares about the invoice). But our
     internal records must be accurate for reconciliation.
   - confirm no changes to the FBR builder are needed

9. Tests:
   - unit: each adapter's validate_input rejects malformed data
   - unit: split tender math (no overpay, no underpay, change correct)
   - integration: full sale with split tender (cash + easypaisa)
   - integration: cheque pending → cleared → applied to invoice
   - integration: cheque bounced → invoice marked unpaid, customer flagged
   - integration: store credit applied + earned consistency

10. Verification:
    - configure all payment methods in admin
    - on POS, complete a Rs 1500 sale split as Rs 1000 cash + Rs 500
      easypaisa, see both tenders, complete cleanly
    - complete a Rs 8000 card sale with manual ref entry
    - complete a Rs 2000 Raast sale, QR shows on customer display
    - issue a Rs 500 store credit to a test customer manually,
      complete a Rs 1000 sale using Rs 500 store credit + Rs 500 cash
    - take a Rs 5000 cheque, see it as 'pending'
    - mark the cheque cleared, see customer ledger updated
    - take another cheque, mark bounced, see invoice flip to unpaid

Constraints:

- The cashier never types the same field twice. If they enter Rs 500
  in the tendered amount, that's it.
- Each method's "happy path" should be under 15 seconds for the cashier.
- Method-specific fields are nullable on payments — the row is shaped
  by payment_method.
- Static QR images for EasyPaisa/JazzCash/Raast are uploaded by the
  tenant in settings; we store and display them. We don't generate
  them in V1.
- The adapter interface is documented so V1.5 can add real API
  integration to EasyPaisa/JazzCash without touching the cashier UI.

Do not write any files yet. Show me the plan.
```

**Approval checklist**:

- [ ] Adapter pattern is real, not a switch statement.
- [ ] Customer-facing display shows QR for QR-based methods.
- [ ] Cheque bounced flow correctly reverses invoice paid status.
- [ ] Split tender math is rigorously tested.
- [ ] Per-tenant method enable/disable works.

---

## Phase 6 — Returns, refunds, customer ledger (week 11)

**Goal**: returns within FBR rules, refunds via the original method, full customer balance/ledger tracking.

**Branch**: `phase-6-returns`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 6), DATABASE_SCHEMA.md section 6
(customer_ledger) and section 8 (returns), SCREENS.md Part A section
A13 and Part C section A4, INTEGRATIONS.md section 1.11 (returns
within FBR rules), and CLAUDE.md.

Phases 0–5 are complete. Sales and payments work fully. Now: returns.

Goal: returns are processed correctly, refunds go to the right place,
customer balances stay consistent.

By the end of this phase I should be able to:

  - process a full return on POS (within 72h → amend; outside →
    credit note via FBR)
  - process a partial return (some lines, some quantities)
  - refund to original method (cash / card reversal / wallet / store
    credit)
  - see the return in admin web with FBR linkage
  - see customer ledger update correctly
  - see inventory restocked for returnable items, written off for
    damaged

Before writing any code, produce a plan covering:

1. Returns app: returns.Return + ReturnItem models per
   DATABASE_SCHEMA.md section 8.

2. POS return flow (SCREENS.md A13):
   - find original invoice (local invoice number, FBR invoice number,
     or by date + amount)
   - load original line items
   - cashier picks lines + qtys to return
   - reason picker (damaged, wrong_item, etc.)
   - refund method picker, defaulting to original method
   - confirm → executes

3. FBR routing logic:
   - if original invoice within 72h AND no items edited: amend the
     original invoice (cancel item OR reduce quantity) via the FBR
     edit/cancel API. Consumes 10% budget.
   - else: create a separate credit_note invoice via PRAL (a new
     invoice with invoice_type='credit_note', referencing the
     original)
   - decision logic in returns.routing module

4. Inventory effects:
   - reason='damaged' or 'expired': stock_movement type='damage' or
     'expiry', no restock
   - reason='wrong_item' or 'customer_changed_mind': stock_movement
     type='return', restocked
   - reason='other': cashier picks restock yes/no

5. Refund to method:
   - cash: drawer opens, cashier hands cash, payment row recorded with
     status='refunded', amount negative
   - card: cashier processes reversal on physical terminal, enters RRN
   - wallet: same
   - store_credit: customer.store_credit increments
   - per INTEGRATIONS.md section 2.7 detail per method

6. Customer ledger:
   - every return writes a customer_ledger row (credit if owed back,
     adjusts running_balance)
   - test: customer balance is always consistent with sum of ledger

7. Admin web (SCREENS.md A4):
   - returns list with filters
   - return detail showing original invoice link, items, refund method,
     FBR linkage (amendment vs credit note)
   - "new return" admin flow for cases the cashier missed (manager+ only)

8. Permissions:
   - cashier can return up to Rs X (per tenant setting)
   - manager PIN above that
   - owner can override anything

9. Tests:
   - within-72h return → original invoice amended, FBR sees update,
     budget consumed
   - outside-72h return → credit note submitted to FBR
   - mixed: 3 items in original, return 1, restock, original goes to
     'partially_cancelled'
   - cross-tenant: cannot return invoice from another tenant
   - ledger consistency after 100 randomized return scenarios

10. Verification:
    - complete a Rs 2000 sale with 4 items
    - 30 minutes later, return 1 item for Rs 500 cash refund
    - see original invoice now 'partially_cancelled', budget consumed
    - 4 days later, return another item — must use credit note path,
      see new invoice in FBR with original referenced
    - customer ledger shows correct running balance throughout
    - inventory: damaged item written off, others restocked

Constraints:

- All refund paths are traceable. Audit log entry for each.
- Customer ledger is append-only via a trigger or model save hook.
  Running_balance is computed at write time, never recomputed lazily
  (consistency over performance).
- Budget consumption on within-72h return is atomic with the FBR
  edit call.
- A failed FBR edit/cancel rolls back the local return state. No
  half-states.
```

**Approval checklist**:

- [ ] FBR routing (amend vs credit note) is deterministic and tested.
- [ ] Customer ledger never gets out of sync with payment/return reality.
- [ ] Inventory effects depend on reason, not just on whether returned.
- [ ] Failed FBR call doesn't leave the local DB in a partial state.

---

## Phase 7 — Reports & analytics (weeks 12–13)

**Goal**: the 18 reports in SCREENS.md, dashboard charts, exports.

**Branch**: `phase-7-reports`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 7), SCREENS.md Part C section A11
in full plus A2 (dashboard), and CLAUDE.md.

Phases 0–6 are complete. The system runs. Now we extract value: reports
and analytics for the owner.

Goal: 18 reports per the spec, plus a populated dashboard, plus
exports.

Before writing any code, produce a plan covering:

1. Reports app: reports module with one file per report. Common shell:
   filter set + query function + serializer.

2. Each of the 18 reports per SCREENS.md A11:
   - daily sales summary
   - hourly sales heatmap
   - item-wise sales
   - category-wise sales
   - top movers / slow movers
   - tax report (FBR-format)
   - profit & loss
   - stock report
   - stock aging
   - cashier performance
   - payment method breakdown
   - returns analysis
   - customer top-N
   - customer dormant
   - supplier purchase summary
   - branch comparison
   - FBR submission report
   - audit log report

   For each: filters, columns, sorting, charts (if any), expected
   query shape (note any that need raw SQL for performance).

3. Heavy reports:
   - any report scanning >10k rows runs as a Celery task
   - emails when ready, also queryable from the reports list with a
     "running" badge
   - cached in Redis for 1 hour
   - cache invalidation on relevant data changes

4. Exports:
   - CSV via streaming response (no memory bloat for big reports)
   - Excel via openpyxl with formatting
   - PDF via WeasyPrint with tenant branding header

5. Dashboard (SCREENS.md A2):
   - KPIs with sparklines
   - 5 charts (revenue trend, sales by hour, by payment method,
     by category, by branch)
   - lists (recent invoices, low stock, failed FBR)
   - all data from materialized aggregates updated on a Celery beat
     cadence (every 5 min during business hours, hourly off-hours)

6. Materialized aggregates:
   - daily_sales_summary table aggregating sales per branch per day
   - product_velocity table aggregating units sold per product per day
   - rebuilt daily; queries hit these instead of raw invoices

7. Saved filters:
   - users can save a report's filter set as a "favorite"
   - favorites list per user

8. Tests:
   - unit: each report's query returns correct data on a known fixture
   - performance: each report on 100k-invoice tenant returns in <5s
     (or moves to Celery)
   - export: CSV, Excel, PDF formats validated

9. Verification:
   - seed a test tenant with 90 days of synthetic data (1000 invoices)
   - run every report, verify numbers match by manual SQL spot-check
   - export each format, open in Excel/Acrobat, verify rendering
   - dashboard loads in <1s with charts populated

Constraints:

- Heavy reports never block the request thread.
- Aggregates are eventually-consistent; dashboard freshness must be
  shown ("Updated 3 minutes ago").
- Money in exports is formatted "Rs. 1,234.56" not "1234.56".
- All report data is tenant-scoped — verified in tests.
```

**Approval checklist**:

- [ ] Heavy reports run async, not in the request cycle.
- [ ] Aggregates have invalidation logic.
- [ ] Exports stream, not buffer in memory.
- [ ] Dashboard freshness is surfaced to the user.

---

## Phase 8 — Polish, hardware, packaging (weeks 14–16)

**Goal**: ship-ready. Animations smooth, performance audited, accessibility checked, Urdu localized, installer signed, onboarding wizard complete.

**Branch**: `phase-8-polish`

**Prompt**:

```
Read PROJECT_PLAN.md section 6 (Phase 8) and section 11 (success
metrics), SCREENS.md Parts E, F, G in full, INTEGRATIONS.md section 3
in full, and CLAUDE.md.

Phases 0–7 are complete. The system works. This phase is about making
it sellable.

Goal: V1 launch readiness.

Before writing any code, produce a plan covering:

1. Animation polish per SCREENS.md Part E:
   - audit every screen for the patterns in the table
   - fix any abrupt transitions, missing hover states, missing focus
     rings
   - ensure all animations respect prefers-reduced-motion
   - 200-300ms ease-out as the default; spring physics where
     specified

2. Performance audit:
   - 95th percentile cashier interaction <300ms locally — measure
   - 95th percentile FBR submission <5s — measure
   - admin web initial paint <1s on 3G — measure
   - identify worst offenders, fix top 3 (likely product grid render,
     report queries, sync polling)
   - add performance tests to CI

3. Accessibility audit per SCREENS.md Part F:
   - keyboard navigation tested on every screen
   - focus rings visible
   - color contrast ≥ 4.5:1 body, 3:1 large text
   - form labels (not just placeholders)
   - error messages descriptive
   - ARIA landmarks
   - prefers-reduced-motion respected
   - screen reader smoke test on POS login + main sale + payment

4. Urdu localization per SCREENS.md Part G:
   - i18next setup
   - extract all POS-cashier-facing strings to en.json + ur.json
   - extract receipt template strings (line items, headers, footers)
   - extract customer display strings
   - extract SMS templates
   - test RTL rendering on POS
   - test Urdu printing on thermal printer (bitmap render path —
     INTEGRATIONS.md section 3.1)

5. Hardware:
   - finish weighing scale serial integration (V1.5 was deferred but
     basic version doable here if time permits — flag if cutting)
   - customer-facing display polish (idle promo rotation, sale-in-
     progress animation, payment QR display, sale-complete celebration)
   - thermal printer compatibility matrix tested per
     INTEGRATIONS.md section 3.8
   - cash drawer test from POS settings

6. Onboarding wizard:
   - "Welcome to your new POS" first-run flow
   - tenant profile completion
   - first branch + terminal setup
   - first product (or CSV import)
   - first sale tutorial (guided, non-blocking)
   - target: <30 minutes from install to first sale

7. Documentation:
   - 5-minute video tutorials for cashier, manager, owner roles
   - in-app help center (SCREENS.md A18)
   - docs site (static, hosted on the same VPS) with searchable
     knowledge base
   - PDF quick-reference cards (cashier shortcuts, day-open, day-close)

8. Electron installer:
   - electron-builder config for Windows (.exe), Linux (.AppImage,
     .deb)
   - code signing certificate (annual cost in PROJECT_PLAN.md section 9)
   - auto-update channel
   - first-launch license activation flow

9. Production deployment:
   - GitHub Actions deploy workflow
   - Nginx + systemd configs per PROJECT_PLAN.md section 8
   - Postgres tuning per DATABASE_SCHEMA.md section 12
   - Backblaze B2 backup schedule
   - Glitchtip self-hosted error tracking
   - UptimeRobot pings

10. Pre-launch checklist:
    - 3 pilot shops running for 2 weeks
    - daily syncs successful
    - all FBR submissions valid
    - cashier feedback positive
    - critical-bug count = 0
    - support runbook documented
    - rollback procedure documented and tested

11. Verification:
    - run a 4-hour load test simulating 50 shops × 100 invoices each
      per day; system stable
    - run accessibility audit tool (axe-core) on every admin page
    - run Lighthouse on admin web, score >90 in all categories
    - install signed Electron app on a fresh Windows 10 box, complete
      a sale within 30 minutes following the in-app onboarding
    - print 100 receipts in succession on a 58mm and an 80mm printer,
      verify quality consistent
    - kill the central server during a sale, verify offline mode
      behavior is graceful
    - restore a backup from 24h ago to a staging environment, verify
      data integrity

Constraints:

- No new features in this phase. Only polish, performance, and
  packaging.
- If something is not ready by week 16, defer to V1.1, not delay V1.
  Document what's deferred.
- The success metrics from PROJECT_PLAN.md section 12 are the gate.
  We don't ship until they're met.
```

**Approval checklist**:

- [ ] Performance metrics measured, not estimated.
- [ ] Accessibility audit passed (axe-core + manual screen-reader smoke).
- [ ] Urdu rendering tested on real thermal printer.
- [ ] Onboarding flow completes in <30 min on a fresh machine.
- [ ] Installer is signed.
- [ ] Backup/restore drill performed and documented.
- [ ] 3 pilot shops live for 2 weeks before declaring V1.

---

## Cross-phase tips

**When Claude proposes something not in the docs**: ask "is this an extension we want, or scope creep?" Either update the doc to make it canonical, or push back.

**When Claude says "I'll add a quick fix"**: the quick fix is technical debt. Make it write the proper fix, or capture the debt explicitly in a TODO.md and address before the next phase.

**When two phases worth of changes accumulate in one PR**: split it. Long-running branches lose review quality.

**When you're tempted to skip tests "just this once"**: don't. The tax-critical paths (Phase 4, Phase 6) get bitten the hardest by missing tests. The system handles real money for real people.

**When you find a bug that should have been caught earlier**: write the regression test first, then the fix. Update the relevant phase prompt's approval checklist so it doesn't recur on V2.

**When CLAUDE.md drifts past 15KB**: prune. Move detail to phase-specific or app-specific CLAUDE.md files inside subfolders. The root file stays lean.

---

*Total estimated time: 16 weeks at ~30 hours/week. Faster if scope is cut, slower if quality bar is raised. The phases are ordered for working software at each step — at the end of every phase, the system is shippable in some form. Don't break that property.*
