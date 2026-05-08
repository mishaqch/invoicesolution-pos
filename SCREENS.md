# Screens — Pakistan POS

> Every screen across the three apps (POS terminal, Customer Display, Admin Web), with components, key actions, and UX notes. Use this as a map; don't copy it verbatim into code.

## Universal UI rules

These apply to every screen across all three apps.

- **Sentence case** on every label, button, heading. "Add product", not "ADD PRODUCT" or "Add Product".
- **One primary action per screen.** It's the only filled button. Secondary actions are outlined or ghost. Tertiary are text links.
- **Touch targets ≥ 44px** on POS, ≥ 36px on admin (mouse-driven).
- **Type scale**: H1 24px / H2 20px / H3 16px / Body 14px / Caption 12px. Two weights only: 400 and 500.
- **Color**: muted neutrals for chrome; ramp colors for state (green=valid, amber=pending, red=error, blue=info, gray=neutral).
- **Spacing**: 8-pt grid. Standard gaps: 8 / 12 / 16 / 24 / 32.
- **Radius**: 8px default, 12px for cards, 6px for inline pills. No fully-rounded buttons except for FABs.
- **Motion**: 200–300ms `ease-out` for most. 150ms for hover/press feedback. 400–500ms for screen transitions. Spring physics for satisfying pop-ins (cart add, payment success).
- **Loading**: skeleton screens, never spinners on screen-level loads. Spinners only inside buttons that are doing work.
- **Empty states**: every list has a designed empty state with an icon, one-line explanation, and a primary action.
- **Error states**: every error has a recovery path. "Something went wrong" is not enough.
- **Keyboard**: every screen is fully navigable by keyboard. Enter submits, Esc closes modals.
- **Sound**: optional, off by default. When on: scan beep (pleasant chime), error (low buzz), success (subtle chime). Never alarm-loud.
- **Dark mode**: supported on admin only. POS stays light (high contrast, predictable for cashiers).

---

# Part A — Cashier (POS terminal, Electron)

The POS terminal is full-screen, always. Cashiers don't multitask. Every screen fills the window.

## 0. Splash → Update check (auto)

On launch, the app:

1. Shows a 1-second splash with logo and version.
2. Pings the central server for app updates (non-blocking).
3. Checks license validity from local store (must heartbeat at least every 30 days).
4. Loads SQLite, restores any `pending_sync` queue.
5. Routes to login.

If offline and license still valid: continues. If license heartbeat overdue >30 days: blocks with reactivation prompt.

## 1. Login screen

**Purpose**: cashier authenticates with PIN.

**Layout**: centered card, ~400px wide. Big logo. "Enter your PIN" prompt. Big numeric keypad (touch-friendly). PIN dots above the keypad fill as digits are entered. Auto-submits on 4–6 digit completion.

**Components**:
- Tenant business name + branch name at top ("Khalil General Store — Defence Branch").
- Cashier-name selector or "I'm a different cashier" link if multiple users assigned to terminal.
- Numeric keypad (10 buttons + clear + backspace).
- PIN dots indicator.
- Manager override button at bottom (small, requires escalation flow).
- Online/offline indicator in corner.

**Animations**: PIN dots fill with subtle scale-up. Wrong PIN = card shake (200ms, 3 oscillations). Successful login = card fade out + slide up.

**Permissions**: anyone with a valid PIN.

## 2. Day open

**Purpose**: declare opening cash float before transactions.

**Trigger**: first login after midnight (or after a closed cash session).

**Layout**: simple form.

**Components**:
- Greeting ("Good morning, Ahmed").
- "Opening cash" field — numeric input with comma formatting.
- Optional: breakdown by denomination (1000, 500, 100, 50, 20, 10, 5, 2, 1, coins). Auto-calculates total.
- Notes field (optional).
- Big "Open day" button.

**Animations**: card slides in from below. Button press → scale 0.95 → success → fade to next screen.

**Side effects**: creates `cash_session` row with status=open.

## 3. Main sale screen

**Purpose**: the heart of the POS. 80% of cashier time spent here.

**Layout** — three-pane horizontal split optimized for 1920×1080 or 1366×768:

```
┌────────────────────────────────────────────────────────────┐
│  Header: branch | terminal | cashier | online dot | Hold   │
├──────────────────┬──────────────────────┬──────────────────┤
│                  │                      │                  │
│                  │                      │                  │
│   PRODUCT GRID   │     SHOPPING CART    │  PAYMENT PANEL   │
│   or SEARCH      │                      │                  │
│                  │                      │                  │
│   Categories     │   Item lines         │  Subtotal        │
│   along left     │                      │  Discount        │
│                  │                      │  Tax             │
│                  │                      │  ────             │
│                  │                      │  TOTAL (huge)    │
│                  │                      │                  │
│                  │   Customer:          │  ┌───────────┐   │
│                  │   [select walk-in]   │  │  CHARGE   │   │
│                  │                      │  └───────────┘   │
└──────────────────┴──────────────────────┴──────────────────┘
```

**Components — header**:
- Branch + terminal labels.
- Cashier name + avatar.
- Online/offline/syncing dot (green/amber/red, with tooltip).
- Pending sync count badge ("3 to sync").
- Hold sale button (parks current cart).
- Recall button (opens held sales list).
- Quick actions menu (...): switch user, lock screen, open day report.

**Components — product grid (left pane, ~40% width)**:
- Search bar at top: barcode scan auto-targets here. Manual text search with debounce.
- Category tabs / quick-pick buttons.
- Grid of product cards, each showing: image (or initial letter if no image), name, price, stock indicator.
- Tap a card → adds to cart (qty 1). Long-press → quantity prompt.
- Numeric keypad below for cashier to type qty before tapping product (e.g., type "3" then tap apples → adds 3 apples).

**Components — cart (middle pane, ~35% width)**:
- One row per line item: product name, qty (with +/− buttons), unit price, line total. Tap row to edit (qty, discount, note, remove).
- Customer slot below items: "Walk-in customer" by default, click to select/create.
- Sub-actions: clear cart, hold sale, apply cart-level discount.

**Components — totals/payment panel (right, ~25%)**:
- Live totals: subtotal, item discounts, cart discount, tax, grand total.
- Total displayed in 36px+ font, bold, right-aligned, animates on change.
- Big primary CHARGE button (orange or brand-primary).
- Quick-pay shortcut buttons under CHARGE: "Cash exact" (auto-completes if cash). "Cash 1000" (common note quickpicks). Optional.
- "Tax inclusive" indicator if applicable.

**Animations**:
- Item add: subtle slide-in from right edge of cart with elastic bounce. Total counter rolls up via animated count-up.
- Quantity change: number scales 1 → 1.1 → 1 with green flash if increasing, red if decreasing.
- Removing line: swipe left on the row reveals delete; or press × icon → row collapses with height animation.
- Charge button: subtle pulse glow when cart non-empty.

**Keyboard shortcuts** (power users):
- `/` — focus search.
- `F2` — customer.
- `F3` — held sales.
- `F4` — apply discount.
- `F9` — charge.
- `Esc` — clear last action / close modal.

## 4. Product search modal

Triggered by clicking search bar or `/`.

**Layout**: full-screen overlay.

**Components**:
- Search input at top (focused).
- Filter chips: category, price range, in-stock only.
- Results grid (same card style as main grid).
- "No results" empty state with "Add quick product" link (manager+ only).

**Behavior**:
- Live search as cashier types (debounced 150ms).
- Results sorted: exact barcode match first → name match → category match.
- Arrow keys navigate, Enter selects.

**Performance**: queries local SQLite, returns within 50ms for 10,000 products.

## 5. Customer selection modal

**Purpose**: link a sale to a registered customer (especially for credit, FBR registered buyers, loyalty).

**Components**:
- Search by phone, name, or CNIC.
- Recent customers list.
- "Add new customer" button (opens 6).
- "Walk-in (unregistered)" pinned at top — default for retail.

**Behavior**: if FBR submission requires registration type and the customer is unregistered, the system uses placeholder buyer details (`buyerNTNCNIC: "0000000000000"`, `buyerRegistrationType: "Unregistered"`), per PRAL acceptance rules.

## 6. Quick-add customer

**Purpose**: minimum-viable customer creation in 30 seconds.

**Components**:
- Name (required).
- Phone (required for credit, optional otherwise).
- CNIC / NTN (optional).
- Address province (defaults to current branch province).
- Registration type: Registered / Unregistered (radio).
- Save & select.

**Validation**: phone in PK format, CNIC 13 digits, NTN 7 digits.

## 7. Line edit modal

Triggered by tapping a cart line.

**Components**:
- Product name + image at top.
- Qty editor (numeric keypad).
- Price override (manager PIN if outside allowed range).
- Discount: % or fixed (each capped per product setting).
- Note (free text, prints on receipt).
- Remove line button (red, confirms if expensive).

## 8. Cart-level actions

Floating bottom-bar buttons accessible while cart has items:

- **Apply discount**: % or fixed off whole cart. Manager PIN if above threshold.
- **Hold sale**: prompts for label (e.g., customer name), saves cart, returns to empty main screen.
- **Clear cart**: confirm dialog. Audited.

## 9. Held sales (recall)

**Purpose**: list all held sales, recall to active cart.

**Components**:
- Each held sale: label, item count, total, cashier name, time held.
- Search/filter (when many held).
- Tap to recall → replaces current cart (warns if current has items).

## 10. Payment screen

**Purpose**: take payment, possibly split across methods.

Triggered by CHARGE button.

**Layout** — full screen replaces main sale until completion or cancel.

```
┌────────────────────────────────────────────────────────────┐
│ ← Back to sale                                Total: 1,847 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   Tendered                Remaining                        │
│   Rs 0                    Rs 1,847                         │
│                                                            │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│   │  CASH    │ │  CARD    │ │ EASYPAISA│ │   RAAST  │      │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│   │JAZZCASH  │ │BANK XFER │ │ STORE CR │                   │
│   └──────────┘ └──────────┘ └──────────┘                   │
│                                                            │
│   [tendered amount input + numeric keypad]                 │
│                                                            │
│   [Add tender] (only if remaining > 0)                     │
│                                                            │
│   [COMPLETE SALE] (enabled when remaining ≤ 0)             │
└────────────────────────────────────────────────────────────┘
```

**Components**:
- Live total at top right, large, animates as tenders are added.
- Tendered / remaining display, very prominent.
- 7 payment-method buttons (color-coded). Disabled buttons are grayed if not configured for tenant.
- Numeric keypad for amount entry (default = remaining).
- For each method picked, opens a sub-flow (see below).
- Tendered list shows each tender with edit/delete.
- "Complete sale" button enabled only when remaining ≤ 0.
- "Cancel" returns to cart preserving everything.

**Sub-flows for each payment method**: see `INTEGRATIONS.md` for full details. UI summary:

- *Cash*: numeric input, suggestion chips (exact, 1000, 5000), shows change due if over.
- *Card (debit/credit)*: cashier swipes on physical terminal (separate device), enters last-4, auth code, RRN. POS doesn't process the card directly — it records the result.
- *EasyPaisa / JazzCash*: shows static merchant QR (full screen), customer scans/pays, cashier confirms with reference number.
- *Raast*: shows Raast P2M QR with amount embedded.
- *Bank transfer*: enter bank, last-4, reference.
- *Store credit*: shows customer's available credit, applies up to that amount.

**Animations**: amount counter rolls down as tenders add. Method buttons press feedback. Successful tender = green flash on tender list. Complete sale = full-screen success state (next screen).

## 11. Sale success screen

**Purpose**: confirm sale complete, show FBR status, reset.

**Layout**: full-screen, brand-positive color (green tint).

**Components**:
- Big checkmark with subtle scale-pop animation.
- "Sale complete" heading.
- Invoice number (local, plus FBR number once received).
- Total + tendered + change.
- FBR status chip: pending / submitting / valid (with FBR number) / failed.
- Receipt preview thumbnail.
- Buttons: print receipt, email/SMS receipt, new sale (large, primary).
- Auto-advance to new sale after 5 seconds (configurable, can be disabled per cashier preference).

**Animations**: checkmark draws stroke-by-stroke (300ms). Confetti or subtle particle burst (toggleable). Page fades to new sale on advance.

## 12. Receipt actions

Triggered from success screen or sales history.

**Print**: sends to thermal printer immediately. Shows progress for 1–2s. Reprint button retries on failure.

**Email**: prompt for email if customer has none on file. Sent via Brevo.

**SMS**: prompt for phone. Sent with link to view receipt online (a public, signed URL valid for 30 days).

**Save as PDF**: generates locally for customer to take on USB.

## 13. Returns / refunds screen

**Purpose**: process a return against a previous sale.

**Layout**: similar to sale screen but reversed.

**Components**:
- Step 1: find original invoice (local invoice number, FBR number, or by date + amount).
- Step 2: load original line items, cashier selects which lines + quantities to return.
- Step 3: refund method (back to original method recommended; or store credit; or cash).
- Step 4: reason (dropdown + notes).
- Confirm → prints credit note receipt → updates inventory (restock or write off based on reason) → submits credit note to FBR → opens drawer if cash refund.

**Constraints**:
- Returns only allowed within FBR's 72-hour window if you want to amend the original; outside that, it's a separate credit note.
- Manager PIN if refund > Rs. X (configurable).
- Cancellation budget (10%) is consumed if amending; informs cashier upfront.

## 14. Day close screen

**Purpose**: reconcile cash drawer at end of shift.

**Layout**: a wizard (3 steps).

**Step 1 — Summary**:
- Sales count, total, by payment method.
- Returns count, total.
- Pull cash from drawer = expected cash.

**Step 2 — Count**:
- Denomination-by-denomination input (or single total).
- Calculates declared vs expected.
- Variance (over/short) shown.

**Step 3 — Reason** (only if variance):
- Variance reason dropdown + notes.
- Manager PIN required if |variance| > threshold.

**On close**: prints day-close receipt (X-report style), closes cash session, locks terminal until next day-open.

## 15. Cashier reports (light)

A small reports section visible to cashiers — only for THEIR shift, not the whole shop.

- My shift summary (current cash session).
- Last 7 shifts.
- My voids/discounts.

Anything else requires manager+ login on admin web.

## 16. Settings (terminal-local)

For configuring this specific install. Manager PIN required.

- Printer setup (test print, paper width, character set).
- Scanner setup (test scan, prefix/suffix config).
- Cash drawer test.
- Customer display toggle.
- Network status / sync diagnostics.
- App version, license info, force sync, log out.

---

# Part B — Customer-facing display

A second monitor showing what's happening in the sale. Optional, runs as a separate Electron window or HTML page.

## C1. Idle screen

When no active sale: shop logo, business name, optional promotional images that rotate every 5s, current date/time, "Welcome" greeting.

## C2. Sale in progress

While cashier is adding items:

- Each scanned/added item appears in a list (newest at top), with name, qty, price, line total. Subtle slide-in animation.
- Running subtotal + tax + grand total at the bottom right, large.
- When item removed: slide out + flash red.
- "Please wait" not shown — cashier sees that, customer sees what they're being charged for.

## C3. Payment in progress

- Same item list (collapsible or summarized).
- Highlighted "Total to pay: Rs. X,XXX".
- For QR-based payments (EasyPaisa, JazzCash, Raast): big QR code visible to customer.

## C4. Sale complete

- Big "Thank you!" + checkmark.
- Auto-emailed/SMS'd confirmation on screen if customer opted in.
- FBR receipt QR code customer can scan to verify on FBR app.
- Auto-returns to idle after 8 seconds.

---

# Part C — Admin web

The owner/manager experience. Web-based, mobile-responsive, runs in browsers. Available even when terminals are offline because it's hosted centrally.

## Universal admin chrome

- **Sidebar (collapsed by default on mobile)**: Dashboard / Sales / Inventory / Catalog / Customers / Suppliers / Reports / FBR / Settings. Icons + labels. Active item highlighted.
- **Top bar**: tenant name + branch selector (if multi-branch user) + global search + notifications bell + user menu.
- **Breadcrumbs**: every screen. Always show how to go back.
- **Branch context**: every report/list defaults to "current branch" but can be switched to "all branches" if user has permission.

## A1. Login

Email + password. Optional 2FA (TOTP for owners). "Forgot password" sends reset link. SSO not in V1.

## A2. Dashboard

The overview screen. Owner gets to see it; manager sees their branch only.

**Top KPIs (cards in a row)**:
- Today's sales (with sparkline, comparison to yesterday).
- Today's transactions.
- Average ticket.
- Top product today.

**Charts (Recharts)**:
- Revenue (last 30 days, line chart).
- Sales by hour (today + yesterday overlay).
- Sales by payment method (donut).
- Sales by category (bar).
- Sales by branch (if multi-branch).

**Lists**:
- Recent invoices (last 10, click to view).
- Low-stock items (top 10).
- Failed FBR submissions (alert if any).
- Cashier-of-the-day (gamification, optional).

**Animations**: charts animate in on first load (300ms ease-out). KPI numbers count up. Skeleton loaders during fetch.

## A3. Sales

### A3.1 All invoices list
Filterable table.

**Filters**: date range, status (all/valid/cancelled/failed), branch, terminal, cashier, payment method, customer, amount range, FBR status.

**Columns**: invoice #, FBR #, date/time, branch, cashier, customer, items count, payment method(s), grand total, status badge, actions (view, print, ...).

**Actions**: bulk export to Excel/CSV/PDF, single-row click → invoice detail.

### A3.2 Invoice detail

**Header**: invoice numbers (local + FBR), status, dates (created, submitted, validated, edited, cancelled), QR code preview.

**Body sections**:
- Buyer info.
- Line items (sortable table). For each: product, qty, price, discounts, taxes, totals. "C" / "E" indicators per line if cancelled/edited.
- Payments table.
- Totals.
- Audit trail (every change with who + when + what).

**Actions** (subject to permissions and FBR rules):
- Print receipt.
- Email/SMS receipt.
- Edit line (within 72h, max 1 edit per item).
- Cancel item (within 72h, within 10% budget, only if not edited).
- Cancel entire invoice (within 72h, within budget, only if no items edited).
- View pre-edit history.

**Constraint indicators**: a clear amber strip across the top if invoice is approaching edit deadline (e.g., "Editable for 11 hours 23 minutes").

### A3.3 Held sales (across all terminals)

Manager view of held sales, can recall on a specific terminal or release.

## A4. Returns

### A4.1 Returns list
Same filter pattern as invoices. Date, branch, original invoice, refund method.

### A4.2 New return
Wizard: search original → select items → reason → refund method → confirm. Same logic as POS-side return flow but admin can do it for any past sale.

### A4.3 Return detail
Like invoice detail. Shows linked credit note in FBR.

## A5. Inventory

### A5.1 Stock by branch
Big table: product, branch, quantity, reorder level, value (qty × cost).

**Filters**: branch, category, low-stock-only, out-of-stock-only.

**Bulk actions**: export, print stock-take sheet.

### A5.2 Stock movements
Append-only history. Filters by product, branch, date, movement type.

### A5.3 Stock adjustments
Manual + reason. Manager+ only. Audited.

### A5.4 Stock transfers
Initiate (from → to), pack/dispatch, receive (with variance reconciliation).

### A5.5 Stock audits (physical count)
Start audit → branch + scope (whole shop, category, single shelf) → counter device fetches list, counter enters counts (can use POS terminal as counter app) → reconciliation report → finalize (creates adjustments).

### A5.6 Low stock alerts
Configurable thresholds, daily digest emails, in-app notifications.

## A6. Catalog

### A6.1 Products list
Big filterable table. Bulk actions: enable/disable, change category, bulk price update, bulk import/export CSV.

### A6.2 Product create/edit

**Sections**:
- Basic: name, name (Urdu), SKU, barcode (with quick-generate button), category, image upload.
- Pricing: cost, sale price, retail price, min sale price, max discount %.
- Tax: HS code (with searchable typeahead), tax rate, taxable yes/no.
- Inventory: track stock yes/no, reorder level, weighable yes/no, batch-tracked yes/no, serialized yes/no.
- Variants: add size/color/etc with per-variant SKU, barcode, prices.
- Description, notes.
- Status: active, deleted.

**Bulk import**: CSV upload, column mapping wizard, preview + validation, commit. Supports updates by SKU.

### A6.3 Categories
Hierarchical tree. Drag to reorder/reparent. Color + icon per category for POS quick-pick.

### A6.4 Tax rates
List + edit. Most tenants use defaults, no need to touch.

### A6.5 HS code browser
Read-only catalog, searchable. Click a product → opens its HS code; click an HS code → see products using it.

## A7. Customers

### A7.1 Customers list
Searchable table. Click → profile.

### A7.2 Customer profile

**Tabs**:
- Overview: contact info, group, balance, store credit, loyalty points.
- Purchase history: invoices, click to drill down.
- Ledger: debits, credits, running balance.
- Notes / activity log.

**Actions**: edit profile, add credit/debit adjustment, send statement, archive.

### A7.3 Customer groups

For tiered pricing. Define group → assign customers → assign discount %.

## A8. Suppliers

### A8.1 Suppliers list
Same pattern as customers.

### A8.2 Supplier profile
Tabs: overview, purchase orders, GRNs, payments, ledger.

## A9. Purchases

### A9.1 Purchase orders list
Filter by status, supplier, date, branch.

### A9.2 PO create/edit
Header (supplier, branch, expected date) + line items (product picker with cost auto-fill) + totals.

### A9.3 Goods receipt
Receive against a PO, partial allowed. Captures supplier invoice number, batch numbers (for batch-tracked products), updates stock + supplier ledger.

## A10. Cash sessions

List of all open + closed cash sessions across all terminals. Drill into any session to see all sales, all payments, variances.

## A11. Reports

A consistent shell for all reports: filters at top, data table + charts in middle, export buttons at top right (CSV, Excel, PDF). Every report can be saved as a "favorite" with its filters.

### Reports list

1. **Daily sales summary** — by terminal, cashier, branch.
2. **Hourly sales** — heatmap by hour × day-of-week.
3. **Item-wise sales** — units sold, revenue, profit per product.
4. **Category-wise sales** — same, aggregated.
5. **Top movers / slow movers** — fastest and slowest selling.
6. **Tax report** — output tax by rate, by HS code, ready for FBR monthly return.
7. **Profit & loss** — revenue − COGS − discounts. Per-period.
8. **Stock report** — current valuation, movement velocity.
9. **Stock aging** — for batch-tracked goods, days-to-expiry buckets.
10. **Cashier performance** — sales/hour, average ticket, void rate, return rate.
11. **Payment method breakdown** — split of cash vs cards vs wallets vs Raast.
12. **Returns analysis** — by reason, by product.
13. **Customer top-N** — top customers by revenue, frequency, recency.
14. **Customer dormant** — haven't visited in N days.
15. **Supplier purchase summary** — by supplier, by period.
16. **Branch comparison** — sales, profitability, traffic.
17. **FBR submission report** — submitted vs failed counts, by day.
18. **Audit log report** — filtered audit trail for compliance.

Each report runs against Postgres. Heavy ones (>5s) move to Celery and email when ready.

## A12. FBR / Compliance

### A12.1 Setup wizard
6-step wizard:
1. Confirm business profile (NTN, STRN, name, etc.).
2. Choose integrator: PRAL (free) or other LI.
3. Select business natures + sector.
4. Provide technical contact details.
5. Approve our static IPs for whitelisting.
6. Sandbox testing dashboard.

### A12.2 Sandbox testing
Card per applicable scenario (SN001…). Status: pending / submitting / success / failed. Click failed for error details. "Run all eligible" button. Production token unlocks once all green.

### A12.3 Production status
Big card showing: integrator name, environment (sandbox/production), token status, last successful submission timestamp.

### A12.4 Submission log
Searchable by FBR number, status, date. Click row → request/response JSON, error details, retry button.

### A12.5 Cancel budget tracker

Big visual:
```
This month's cancel budget: Rs. 24,500
Consumed:                    Rs. 18,400 [bar 75% filled]
Remaining:                    Rs.  6,100
Resets in: 9 days
```

Per-invoice consumption history below. Alerts when consumption > 80%.

### A12.6 Manual amendment escape hatch
For when an invoice missed the 72-hour window: directs user to log into IRIS, walks them through the manual cancellation/edit screen there. Out of our control but we provide guidance.

## A13. Branches

### A13.1 List + map
Cards or table view. "Add branch" if user has permission.

### A13.2 Branch settings
Address, phone, FBR POS ID, receipt overrides, working hours, timezone.

## A14. Terminals

### A14.1 List
Per-terminal: branch, name, app version, last seen, sync health.

### A14.2 Terminal detail
Hardware config, recent invoices, recent sync events, force-resync button.

## A15. Users & permissions

### A15.1 Users list
Add/invite/edit/deactivate. Bulk import.

### A15.2 User detail
Profile, role, branch access, custom permission overrides, activity log.

### A15.3 Roles
View role permission matrices. V1 doesn't allow custom roles, only the 5 predefined.

## A16. Audit log
Big filterable searchable view of `audit_log`. Filters by user, entity, action, date. CSV export. Cannot edit/delete (it's truly append-only).

## A17. Settings

Sub-pages:

- **Business profile** — name, NTN, STRN, logo, address. Owner only.
- **Receipt customization** — header text, footer text, logo placement, paper width, language preference.
- **Tax settings** — default rate, tax-inclusive pricing toggle.
- **Payment methods** — enable/disable methods, configure each (EasyPaisa merchant ID, JazzCash MID, etc).
- **Notifications** — daily report email recipients, low-stock alerts, FBR alerts.
- **Hardware** — supported printers, default paper width.
- **Backup & restore** — last backup time, manual backup, download backup, restore (dangerous, requires owner + 2FA).
- **Subscription & billing** — current plan, next invoice, upgrade/downgrade.
- **Danger zone** — close account.

## A18. Help / docs

Embedded help system: searchable knowledge base, video tutorials, "Contact support" form, system status page.

---

# Part D — Mobile (V2, deferred)

A small React Native app for owners on the go. Read-only initially.

- Today's sales (live).
- Approve/reject pending discounts (push notification).
- View any branch's daily summary.
- Receive critical alerts.

Don't build this in V1. It's a distraction.

---

# Part E — Animation reference

A consolidated list of the motion patterns used across the system. Keep these consistent.

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Page transition | Route change | fade + 8px upward slide | 250ms | ease-out |
| Modal open | User action | scale 0.96→1 + fade in | 200ms | ease-out |
| Modal close | User action | fade out + scale 1→0.98 | 150ms | ease-in |
| Cart item add | Cashier adds item | slide in from right + spring scale | spring (stiffness 300, damping 25) | — |
| Cart item remove | Cashier removes item | height collapse + fade | 200ms | ease-in |
| Total counter change | Cart totals update | rolling number animation | 400ms | ease-out |
| Button press | Click/tap | scale 0.97 + filter darken | 100ms | ease-out |
| Toast notification | System message | slide down from top + bounce | 300ms | spring |
| Success state | Sale complete | check stroke draw + subtle particle burst | 400ms (check) + 800ms (particles) | ease-out |
| Skeleton loader | Data loading | shimmer left-to-right | 1500ms loop | linear |
| Card hover (admin) | Mouse over | subtle shadow + border tint | 150ms | ease-out |
| Sidebar collapse | Click toggle | width transition | 250ms | ease-in-out |
| Form field focus | Input focused | border color + ring | 150ms | ease-out |
| Input invalid | Validation fail | shake (3 oscillations) | 250ms | — |
| Login screen wrong PIN | Wrong PIN entered | card shake | 200ms | — |
| Drawer slide | Side panel open/close | translateX | 300ms | ease-in-out |
| Tab switch (admin) | User clicks tab | underline slide + content cross-fade | 200ms | ease-out |

Implement these via Framer Motion (`motion`) for React. CSS transitions are fine for hover/focus states. Avoid `setInterval`-driven animations.

---

# Part F — Accessibility checklist (per screen)

- [ ] All interactive elements reachable via Tab. Focus rings visible.
- [ ] Color is not the only signal. Status badges include icon + text.
- [ ] Contrast ratio ≥ 4.5:1 for body text, 3:1 for large text.
- [ ] Form fields have labels (not just placeholders).
- [ ] Error messages are descriptive, not just "Invalid".
- [ ] Modals trap focus until dismissed. Esc closes.
- [ ] Screen reader landmarks (main, nav, banner) on every page.
- [ ] Animations respect `prefers-reduced-motion`.
- [ ] Touch targets 44px minimum on POS, 36px on admin.
- [ ] Tables have proper `<th>` headers with scope.

---

# Part G — Localization

V1 ships English + Urdu for:
- POS terminal (cashier-facing strings).
- Receipt templates (line items, headers/footers).
- Customer display (greetings, totals).
- SMS templates.

Admin web is English-only in V1. Add Urdu in V1.5 when there's customer demand.

Storage: `i18next` keys, locale files in `shared/locales/`. Strings are sentence case in English, RTL-supported in Urdu.

For Urdu printing on thermal printers: ESC/POS supports a code page for Urdu (CP864 partially; better is to render text → bitmap → print as image, which is what we'll do for Urdu lines). Slower but reliable.

---

*Wire frames live in Figma; this doc is the textual contract. If a wireframe contradicts this file, this file wins.*
