# Deferred to V1.5+

Scope cuts from V1. Each entry says **what** was cut, **why**, and
**how to add it later** without disrupting V1.

The Phase 8 prompt is explicit: "If something is not ready by week 16,
defer to V1.1, not delay V1. Document what's deferred." This file is
that document.

---

## Weighing scale serial integration

**What:** Live weight reading from a serial-port scale (CAS, Avery
Berkel, etc.) into the cart on the POS terminal.

**Why deferred:** None of the three pilot shops use scales — they sell
unit-priced goods. Building the adapter without a real scale to test
against is speculative. The Phase 8 prompt explicitly allowed cutting
this with the note "flag if cutting".

**What V1 does instead:** Cashiers enter quantity manually for
weighable products. The `is_weighable` flag on `Product` is honored
by the pricing engine (rate × qty math is identical), so the math is
already correct. The unit grid still works.

**How to add in V1.5:**
1. Add `serialport` (^12) + `@serialport/parser-readline` to
   `pos-terminal/package.json`.
2. New `pos-terminal/electron/scale.ts` with an adapter pattern
   (`readScale(): Promise<{ weight_kg: string; stable: boolean }>`).
3. Per-station config row in local SQLite meta:
   `scale.port` (e.g. `/dev/cu.usbserial-X`), `scale.baudrate`,
   `scale.dialect` (`cas-ed-h`, `avery-berkel-fx50`, etc.).
4. Hardware settings page already has the test UI — just enable the
   placeholder.
5. Wire into the cart: when adding a `is_weighable` product, fire
   `window.api.scale.read()` and prefill the qty input.

**Estimated effort:** 1 week including a real scale to test against.

---

## Direct API integration with EasyPaisa / JazzCash

**What:** Server-side polling for wallet payment confirmation, dynamic
QR generation, automated reconciliation.

**Why deferred:** Both providers require business-account vetting that
takes weeks. V1 uses static merchant QRs uploaded by the tenant — the
cashier confirms the customer's reference number on screen.

**What V1 does instead:** Manual reference entry per
`apps/payments/adapters/wallet.py` validate_input. Cashiers see the
customer's app screen for the reference number before pressing
"Process payment".

**How to add in V1.5:**
- Wallet adapter is already abstracted (`apps/payments/adapters/`).
  Drop in a new `record_payment` implementation that calls the
  provider's webhook instead of trusting cashier input.
- Add a webhook endpoint at `/api/payments/webhooks/<provider>/`.

---

## Backbone of Phase 9 (platform / super-admin)

**What:** Full self-service signup, automated subscription billing,
support tickets, impersonation, business analytics dashboard.

**Why deferred:** The full document explicitly says Phase 9 lands
**after** V1 ships with at least 5 paying customers and 10
manually-onboarded tenants providing operational learnings. Building
billing automation before you know the actual unit economics is
speculative.

**What V1 has instead:** The Phase 0 platform stub. Three subscription
plans seeded, `Tenant.signup_source` + `account_manager` +
`suspended_at` tracking, JWT carries `is_platform_staff`, tenant API
gates platform staff out of `/api/...`. Manual onboarding via Django
admin works for the first ~10 customers.

**Path forward:** Phase 9 prompt in `CLAUDE_CODE_PROMPTS.md` with the
sub-phase plan (9.1 signup + billing, 9.2 support + monitoring,
9.3 analytics + config).

---

## Reseller / white-label (V2)

**What:** Reseller portal, custom branding per reseller, custom domain
routing, revenue share calculation, monthly payout flow.

**Why deferred:** Speculative. The document says "Don't build this
until you have at least one serious reseller candidate signed up
with a clear deal."

**What V1 has:** No reseller code paths. The `tenants.Tenant` model
has zero reseller fields. Phase 9 also keeps the reseller models
unbuilt.

---

## Real PRAL production cutover

**What:** A real taxpayer (NTN + STRN) onboarded in PRAL sandbox,
running scenario tests, getting a production token.

**Why deferred:** Requires actual customer NTN. V1 ships the entire
integration; a tenant follows the in-app `/fbr/setup` wizard during
onboarding to plug in their token.

**What V1 has:** Full FBR integration code + 15 sandbox scenarios,
all behind a `FbrToken` model that's empty until the tenant
configures it.

---

## Lighthouse / axe-core CI checks

**What:** Automated accessibility + performance audits in CI on every
PR.

**Why deferred:** Both tools need a real Chromium browser running in
the CI environment, plus the admin-web dev server up. The current CI
workflow (`ci.yml`) runs lint + typecheck + pytest; adding a
browser-based job means installing Chromium and starting the dev
server, which roughly doubles CI duration. Worthwhile when actively
optimizing; overkill when no one is reading the audit reports.

**What V1 has:** Manual `prefers-reduced-motion` honored, focus-visible
rings on every interactive element, semantic landmarks on the admin
shell, color contrast meeting WCAG AA. `PERF_BUDGET.md` documents the
expected metrics.

**How to add later:** GitHub Actions `pa11y-ci` action or
`@axe-core/cli` on the running dev server. Lighthouse CI image
publishes scores as a PR check.

---

## Hardware test on real thermal printers

**What:** Verifying receipt + Urdu rendering + drawer kick on the
specific Pakistan-market printers (EPSON TM-T20III, Xprinter XP-58,
Bixolon SRP-330II).

**Why deferred:** Requires physical printers. The `node-thermal-printer`
adapter is wired and tested at the formatter level
(`__testing.renderReceiptText`); the actual ESC/POS bytes vary per
device and need real hardware to verify.

**What V1 has:** The adapter is pluggable, dialect-aware
(`epson` vs `star`), and supports both 80mm + 58mm widths. The
`/hardware` page lets each station configure its printer URL.
Receipts log to disk when no printer is attached so cashier flow
never blocks.

**Pre-launch step:** Run the printer compatibility matrix from
`INTEGRATIONS.md` section 3.8 against real hardware before pilot
shop bring-up.
