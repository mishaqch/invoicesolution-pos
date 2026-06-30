# Hotel Guest Folio (multi-day stay) — Implementation Plan

## Context
TDCP-style resort clients offer **rooms + restaurant**. A guest checks in (e.g. Jun 30),
stays days, orders food/tea/snacks throughout, and checks out (e.g. Jul 10). Remembering
10 days of orders to bill at the end is the pain point. We build a **guest folio**: the
cashier opens ONE stay (guest name, CNIC, phone, optional email/address, check-in/out,
room), adds charges day-by-day, and at checkout prints ONE consolidated bill.

**Only for rooms+restaurant clients** (a new `hotel` capability). Restaurant-only / pizza
clients are unaffected.

## Decisions (locked with the user)
- **Dedicated `GuestFolio` model** groups many daily charge-invoices → one consolidated bill.
- **Rooms use a FIXED tax AMOUNT per night** (not %), scaled by nights × rooms:
  VIP base 8,820 + tax 1,680 = **10,500**; Deluxe 6,300 + 1,200 = **7,500**;
  Standard 5,040 + 960 = **6,000**. (Restaurant items keep **16%**.)
- **16 individual rooms** tracked (VIP-1..5, Deluxe-1..5, Standard-1..6) for occupancy.
- **Room nights auto-computed** from check-in→check-out; restaurant items added manually.
- **Tax fixed** (16% food / fixed-amount rooms) regardless of pay method; method chosen at checkout.
- **Managed on the POS terminal** (offline-first).

## Architecture — folio = grouping over proven invoice machinery
The terminal is offline-first; the sync layer already syncs `invoice` + `customer`
idempotently. Rather than invent a new offline entity, **each "charge entry" a cashier
adds is a normal Invoice** (the existing held/checkout path that already syncs). The
`GuestFolio` is the **grouping record** that ties those daily charge-invoices together and
computes the consolidated bill. This gives multi-day folios WITHOUT rewriting offline sync.

```
GuestFolio (1) ───< FolioInvoice (link) >─── Invoice (N)   # each = one charge entry
   guest info, room(s), check_in/out, status(open/closed)
```

- Opening a stay → creates a GuestFolio (server) with guest + room + dates; room-nights are
  posted as the first charge-invoice automatically (nights × room nightly base + fixed tax).
- Adding charges any day → a small Invoice (restaurant items) linked to the folio. Syncs
  via the existing `invoice` path; we add `folio_id` to the sync payload.
- Checkout → folio.status=closed; consolidated bill = sum of all linked invoices; one
  printed bill listing every charge grouped by day.

## Backend

### Models (`apps/hotel/` — new app)
- **Room**: tenant, branch, room_number, room_type (vip/deluxe/standard or free text),
  nightly_base (Decimal), nightly_tax (Decimal, FIXED amount), status (available/occupied/
  maintenance), is_active, deleted_at.
- **GuestFolio**: tenant, branch, folio_number (per-branch sequence), guest_name,
  guest_cnic, guest_phone, guest_email (blank), guest_address (blank), room (FK Room,
  nullable for multi-room later), check_in (DateTimeField), check_out (DateTimeField,
  nullable until checkout), nights (computed), status (open/closed/cancelled), opened_by,
  closed_at, notes, created/updated. 6-yr-retention friendly (soft signals, audit).
- **FolioInvoice**: folio FK + invoice FK (OneToOne to Invoice) + kind (room/restaurant/
  misc) + charge_date. Groups every charge entry under the folio.
- **Tax for rooms**: room nights post a SaleItem with `tax_amount` set to the FIXED
  per-night tax × nights (we bypass %-based tax for room lines using the existing
  cart-line tax override path — SaleItem already stores an explicit `tax_amount`).

### Services (`apps/hotel/services.py`)
- `open_stay(...)` → validate room available; create GuestFolio; auto-post the room-night
  charge-invoice (nights = ceil(check_out−check_in) or 1 if same-day; line = room product,
  qty=nights, unit_price=nightly_base, tax_amount=nightly_tax×nights). Mark room occupied.
- `add_charge(folio, cart_lines, ...)` → create a normal Invoice (restaurant items, 16%
  via product tax_rate) linked to the folio via FolioInvoice. Reuses `checkout.create_invoice`.
- `checkout_stay(folio, payments, ...)` → close folio, free the room, set check_out,
  compute consolidated totals across all linked invoices, record payment(s) against a
  settlement invoice (or per-invoice). Returns the consolidated bill payload for printing.
- `consolidated_bill(folio)` → structured data: guest, room, nights, room charges,
  itemized restaurant charges grouped by date, subtotal, tax (split: room fixed + food
  16%), grand total, amount paid.

### API (`apps/hotel/urls.py` → `/api/hotel/`)
- `GET /rooms/` (list + availability), `POST /rooms/` (admin).
- `GET /folios/?status=open` (open stays for the terminal Stays screen).
- `POST /folios/` open_stay. `GET /folios/{id}/` detail + consolidated bill.
- `POST /folios/{id}/charges/` add_charge. `POST /folios/{id}/checkout/` checkout_stay.
- All gated on a new `hotel` module + tenant capability.

### Gating — new `hotel` capability
- Add `hotel` to the module registry (`apps/tenants/modules.py`) + to POS default modules
  ONLY when explicitly enabled (NOT auto-on for every POS tenant — restaurant-only clients
  must not see it). A tenant is "rooms+restaurant" when `modules_enabled` contains both
  `restaurant` and `hotel`. Expose via `/api/me/modules/` so terminal + admin-web gate on it.
- TDCP gets `hotel` added; the pizza/restaurant-only demo does not.

### Migration + seed
- New `apps/hotel` migrations (Room, GuestFolio, FolioInvoice).
- Update `seed_tdcp_demo`: replace the 4 placeholder rooms with the REAL 3 types as
  products (VIP/Deluxe/Standard, nightly_base + fixed nightly_tax), create the 16 Room
  rows, enable the `hotel` module on the TDCP tenant.

## Terminal (pos-terminal) — offline-first Stays flow
- New **"Stays / Guests"** area (gated on the `hotel` module), alongside the existing till.
- **Open stay**: form — guest name*, CNIC*, phone*, email, address (optional), room type +
  available room, check-in (default now), expected check-out (date+time pickers) → posts
  open_stay; room-nights auto-charged.
- **Open stays list**: shows each guest, room, check-in, running total. Tap → folio detail.
- **Folio detail**: running list of all charges (room + each day's food) with running total;
  an **"Add charges"** button drops into the normal product till scoped to this folio
  (adds a restaurant charge-invoice linked to the folio). Works offline (queued like any sale).
- **Checkout**: shows the consolidated bill (room nights + all food grouped by day, tax
  split, grand total), pick payment method (cash default → 16%/fixed tax already baked),
  settle → prints ONE consolidated non-fiscal bill on the thermal printer, frees the room.
- Receipt: extend `printer.ts` with a `renderFolioBill()` for the consolidated stay bill
  (guest + room + nights + dated sections + totals), non-fiscal (is_fiscal=false for TDCP).

## Admin-web (light, manager view)
- A **Stays** screen (gated on `hotel`): list folios (open/closed), open a folio to view the
  consolidated bill + charge history. Rooms management (CRUD + occupancy) under a Hotel
  section. Reuses existing table/list patterns. (Cashier still drives day-to-day on the till.)

## Critical files
- New: `backend/apps/hotel/{models,services,serializers,views,urls,admin,apps,migrations}.py`;
  `apps/hotel` in INSTALLED_APPS; `/api/hotel/` in core/urls.
- Edit: `apps/tenants/modules.py` (+`hotel`), `business_mode.py` (don't auto-enable),
  `seed_tdcp_demo.py` (rooms + enable hotel), `apps/sync/services.py` (accept optional
  `folio_id` on invoice ingest → create FolioInvoice link).
- Terminal: new `src/routes/stays.tsx` + `src/features/hotel/*`; `electron/printer.ts`
  `renderFolioBill`; sale store + sync payload carry `folio_id`; gate on `hotel` module.
- Admin-web: `src/routes/hotel/*` (rooms, stays) + App.tsx routes gated on `hotel`.

## Verification
- Backend tests: open_stay computes nights+room tax; add_charge links to folio; checkout
  consolidates; room occupancy flips; gating (non-hotel tenant 403). `manage.py check` +
  migration check.
- Terminal: typecheck + electron-vite build. Manual: open stay → add charges across "days"
  → checkout → one consolidated bill prints; works offline (queue) then syncs.
- Regression: restaurant-only tenant sees NO Stays UI; normal sales unaffected.

## Phasing (so it ships safely)
1. **Backend** (models, services, API, gating, migration, seed, tests) — deploy + reseed.
2. **Terminal Stays flow** (open/list/add-charge/checkout + folio bill print) — build .exe.
3. **Admin-web** Stays/Rooms management (manager view) — deploy.
Each phase is independently verifiable; the user demos after phase 2.

## Out of scope (this pass)
Online booking/availability calendar, multi-room-per-folio (single room first; model allows
later), partial/split payments across the stay, refunds/early-checkout proration, housekeeping
status workflow. Folio is non-fiscal for TDCP (no FBR), consistent with existing setup.
