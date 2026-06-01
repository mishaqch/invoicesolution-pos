# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

**This repo is well past the spec-only stage.** It now holds a full Django backend (`backend/apps/*` — accounts, catalog, sales, fbr, sync, tenants, …), a built admin web (`admin-web/`), an Electron offline-first POS terminal (`pos-terminal/`), and a customer display (`customer-display/`). Digital Invoicing (admin-web → FBR) works end to end; the POS terminal (sale → local SQLite → sync → FBR) is largely working with barcode scanning, thermal + A4 printing, and FBR logo/QR. Treat the four design docs below as **intent**, not current state — read the code for ground truth, and update the docs when scope shifts.

Build/run gotcha: the POS terminal needs Node 20 (`.nvmrc`), and `better-sqlite3` is compiled against Electron's ABI — running its DB code under plain `node` fails with `NODE_MODULE_VERSION`. Use the app/electron-vite, or the `sqlite3` CLI, to poke the DB.

The structure described in `PROJECT_PLAN.md` § 5 ("Project structure (monorepo)") is the contract for where new code goes.

The four documents are mutually load-bearing — when answering a non-trivial question, read the relevant ones together rather than guessing from one:

- [PROJECT_PLAN.md](PROJECT_PLAN.md) — vision, stack choices (with reasons for what was rejected), 16-week phased roadmap, hosting/cost model, risk register
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — every Postgres table, field type, index, and tenancy rule
- [SCREENS.md](SCREENS.md) — every cashier and admin screen with components, flows, animations, and permission gates
- [INTEGRATIONS.md](INTEGRATIONS.md) — FBR/PRAL wire format, payment methods, hardware (ESC/POS, scanner, drawer)

If you change scope, update the doc in the same change. The plan file calls itself "the contract."

## What we are building

A hybrid offline-first + cloud-sync, **FBR-compliant** POS for Pakistani retailers. Three apps share one Django backend:

1. **POS terminal** — Electron + React + local SQLite. Runs on a 2-core / 4 GB Windows machine in a shop. Must keep working through power cuts and internet outages.
2. **Admin web** — React + Vite + Tailwind + shadcn/ui. Owner/manager dashboard.
3. **Customer-facing display** — small static React page rendered by the terminal's Electron process on a second monitor.

Backend: Django 5 + DRF, PostgreSQL 16, Redis 7, Celery. Single VPS (Contabo/Hetzner, ~$10/mo). **No managed cloud services** — the entire infra cost target is under $22/mo for the first 100 customers.

## Architecture invariants (do not violate without discussion)

These are the rules that the rest of the system depends on. Most are spelled out across the docs but easy to miss:

- **Terminals never talk to PRAL directly.** All FBR traffic flows through the central Django server, which holds the static IPs PRAL whitelists (max 3). Designing per-terminal direct integration breaks at customer #4. (`PROJECT_PLAN.md` § 4)
- **Offline-first writes.** The cashier UI never blocks on the network. Every sale is written to local SQLite with `status='pending_sync'` first; the cloud is reconciled by a background queue. UI shows a green/amber/red dot, not a spinner. (`PROJECT_PLAN.md` § 4 data flow)
- **Idempotency on every sync POST.** Client-generated UUID per write. Server is idempotent. Networks fail mid-request — that is the normal case, not the exception.
- **Audit, don't delete.** User-facing tables (products, customers, invoices) use `deleted_at` soft delete. Every meaningful state change appends to `audit_log` with before/after JSON. **Six-year retention is a legal requirement.**
- **PRAL response is the source of truth.** Once an invoice has an `FBR Invoice Number`, never modify it locally. Local data is a cache.
- **Multi-tenancy is row-level via `tenant_id`** (not schema-per-tenant). Every queryset MUST filter by `tenant_id`; every composite index leads with `tenant_id`. Global lookups (`hs_codes`, `units_of_measure`) are the only exceptions. (`DATABASE_SCHEMA.md` § conventions)
- **Money is `DECIMAL(14,4)` in Postgres, `Decimal` in Python, integer paisa in JS/TS.** Never `float`. This is in the code-review checklist for a reason.
- **72-hour edit window and 10% monthly cancel cap are enforced server-side**, not just in the UI. Both are hard FBR rules.
- **Invoice numbers are monotonic per terminal per day.** Gaps are anomalies and get flagged.

## FBR / PRAL specifics that bite

The integration has several non-obvious quirks documented in [INTEGRATIONS.md](INTEGRATIONS.md) Part 1. Highlights:

- The wire format wants `rate` as a **string** like `"18%"`, not a number.
- `uoM` is a verbose enum string (`"Numbers, pieces, units"`, `"Kilograms"`) — keep a constant map.
- For unregistered walk-in customers, use `buyerNTNCNIC: "0000000000000"` (13 zeros).
- `scenarioId` is required during sandbox testing only; omit in production.
- Tokens are per-environment + per-taxpayer, long-lived, no documented refresh. Store encrypted (Fernet, key from env) in `fbr_tokens.token_encrypted`.
- All FBR JSON construction lives in **one** module (`backend/apps/fbr/builder.py`) so the wire format has a single owner.

For tax-critical paths (FBR submission, taxes, cancel-budget, money math): write the test first with explicit expected inputs/outputs, then implement. The plan calls this out as the path to fewest bugs in the parts that matter most.

## When you start writing code

The repo has no scaffolding yet. The first time someone implements Phase 0 (`PROJECT_PLAN.md` § 6):

- Stand up the directory tree from `PROJECT_PLAN.md` § 5 — `backend/`, `admin-web/`, `pos-terminal/`, `customer-display/`, `shared/`.
- A `docker-compose.yml` at the root brings up Postgres + Redis + Django for local dev.
- The `shared/` folder holds TypeScript types used by all three frontends; this is the whole reason for the monorepo.
- CI is GitHub Actions (`.github/workflows/{backend-ci,admin-ci,pos-build}.yml`).

Until that scaffolding exists, there are no build/test/lint commands to run.

## Code-review checklist for generated code

From `PROJECT_PLAN.md` § 7. Apply these to anything you write:

1. All monetary values stored as `Decimal` (Python) or integer paisa (JS) — never `float`.
2. Every API endpoint protected by the right permission (see role matrix in `DATABASE_SCHEMA.md` § 1).
3. Every database write inside a transaction.
4. Every external call (PRAL, payment gateway) wrapped in retry with timeout — no infinite waits.
5. Tests for the unhappy path, not just the happy path.
6. Logging is enough to debug a production issue without being chatty.

## Things that are intentionally not in V1

So you don't accidentally build them: mobile app, multi-currency, loyalty programs, e-commerce sync, restaurant-specific features (tables/KDS), salon workflows, provincial sales tax (SRB/PRA), AI recommendations, white-labeling. These are all explicitly deferred to V2 in `PROJECT_PLAN.md` § 13.
