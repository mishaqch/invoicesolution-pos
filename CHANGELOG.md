# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.0.1] — Phase 0 (Foundation)

### Added
- Monorepo scaffolding: `backend/`, `admin-web/`, `pos-terminal/`, `customer-display/`, `shared/`.
- `docker-compose.yml` with Postgres 16, Redis 7, Django, Celery worker, Celery beat.
- Django backend with `accounts` and `tenants` apps:
  - Custom `User` model (email-as-username, Argon2id password + PIN).
  - `Tenant` and `TenantMembership` models.
  - `TenantContextMiddleware` resolves `request.tenant` from JWT or membership.
  - `TenantScopedManager` + Django system check for tenant-scoped models.
  - JWT auth (15 min access / 7 day refresh, rotation + blacklist) with custom claims (`tenant_id`, `role`).
  - PIN-based fast login endpoint for cashiers.
- Admin web shell (Vite + React + TypeScript + Tailwind + shadcn/ui): login screen, protected dashboard with universal admin chrome.
- POS terminal shell (Electron + React + better-sqlite3): splash → PIN keypad login → empty sale screen. SQLite schema for `outbound_queue` reserved.
- Shared TypeScript types consumed by both frontends.
- GitHub Actions CI: lint + typecheck for all three apps, pytest for backend.
- Root README with first-time setup and run instructions.

### Deferred to later phases
- Catalog, inventory, sales, FBR, payments, returns, reports — empty app folders reserve directory layout.
- Offline PIN login (Phase 3, with sync engine).
- Branches and terminals as DB models (Phase 1+); POS uses .env stubs in Phase 0.
- `audit_log` and `sync_log` server-side tables (Phase 2/Phase 3).
