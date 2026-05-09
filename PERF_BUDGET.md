# Performance budget

Phase 8 added explicit budgets. Numbers below are targets, not guarantees;
run the verification steps before declaring V1 ready.

## Frontend

| Metric                                      | Budget      | How to measure |
|---------------------------------------------|-------------|----------------|
| Admin web initial JS (gzipped)              | < 250 KB    | `npm run build` then check `dist/assets/*.js` sizes |
| Admin web first contentful paint, 3G        | < 1 s       | Chrome DevTools → Lighthouse, mobile, slow 3G |
| Admin web Lighthouse score                  | ≥ 90        | Lighthouse on `/` and one report page |
| POS terminal cashier interaction p95        | < 300 ms    | Click → response timing in dev tools, scan-to-cart hot path |
| POS terminal first paint after Electron splash | < 800 ms | `console.time` in `main.tsx` |

The Vite manual-chunks split (react-vendor / query-vendor / form-vendor)
landed in Phase 8 to keep the initial bundle under budget once dashboard
+ reports + onboarding code shipped.

## Backend

| Metric                                      | Budget      | How to measure |
|---------------------------------------------|-------------|----------------|
| Median sales-list endpoint                  | < 100 ms    | Django Debug Toolbar / SQL count |
| FBR submission p95 (server roundtrip)       | < 5 s       | Logged in `fbr_submissions.duration_ms` |
| Daily aggregates rebuild for one tenant     | < 2 s       | Beat task duration log |
| `/api/reports/dashboard/` p95               | < 400 ms    | DEBUG=True profile or curl timing |

Out-of-budget reports are routed to async (Celery `run_async_report`) when
the filter range exceeds 30 days; the API returns 202 + a ReportRun row.

## Infra

| Metric                                      | Budget      |
|---------------------------------------------|-------------|
| 50 concurrent shops, 100 invoices/day each  | system stable, no 5xx beyond noise |
| One full day of sync logs                   | < 200 MB    |
| Daily backup to Backblaze B2                | < 60 s      |

## Verification (deferred — needs real environment)

1. Lighthouse against staging admin web; capture report into `docs/perf/`.
2. axe-core scan on every admin page.
3. 4-hour load test simulating 50 shops × 100 invoices/day; observe DB CPU.
4. Print 100 receipts on each of the supported thermal printers
   (INTEGRATIONS.md §3.8).

When any item drifts out of budget, fix it before adding new features.
The cost of pulling a perf regression is much lower at PR time than after
ship.
