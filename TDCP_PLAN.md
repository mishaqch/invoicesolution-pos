# TDCP Kalar Kahar — Non-Fiscal Resort POS (Rooms + Restaurant)

## Context
TDCP (Tourism Development Corporation of Punjab) runs resorts with **rooms** and a
**restaurant**. They want to print **plain invoices** (rooms, restaurant, or both on one
bill) on a counter thermal printer — **no FBR/PRA fiscalization** (no FBR logo, QR, or
number) for now, possibly later. First site: **Kalar Kahar resort** (one branch), but the
design must support **multiple resorts** (each = a branch) later. Goal: a polished, live
demo on a laptop terminal for TDCP managers, with **easy connectivity** (no FBR POS
ID/passcode — just our pairing code).

## Key finding: ~80% already exists
The codebase already has, working end-to-end: the **restaurant vertical** (tables,
modifiers, order types, KOT), **thermal ESC/POS printing** (58/80mm, drawer kick),
**multi-branch/terminal**, and **terminal pairing that needs only our `pairing_code` +
device fingerprint — NOT the FBR POS ID** (`backend/apps/tenants/serializers.py`
TerminalPairSerializer). `fbr_pos_id` is a separate, nullable field used only at
fiscalization. So a TDCP terminal pairs and runs with zero FBR setup today.

The real work is three surgical pieces: a **non-fiscal mode**, a **non-fiscal receipt
layout**, and **Rooms as a first-class category**.

---

## 1. Backend — non-fiscal tenant mode
Add a third `fbr_connection_type` value `"none"` (alongside `di_api`, `ims_sdc`).
- `backend/apps/tenants/business_mode.py`: add `("none", "Non-fiscal (no FBR/PRA)")` to
  `FBR_CONNECTION_TYPES`.
- `backend/apps/fbr/tasks.py` `submit_invoice_to_fbr`: **early return** when
  `tenant.fbr_connection_type == "none"` → `{"skipped": "non_fiscal"}`. The invoice is
  created + synced + reportable, but never touches FBR; it stays a normal local invoice
  with `fbr_invoice_number = NULL`.
- Expose `fbr_connection_type` (already returned by `/api/me/modules/`) so terminal +
  admin-web know the tenant is non-fiscal and hide all FBR UI.
- Migration: none needed (it's a new choice on an existing CharField); verify with
  `makemigrations --check`. Add a tiny migration only if Django wants one for choices.

**Why this over "just leave the token empty":** explicit, reusable for any future
non-fiscal client, and the invoice never sits in a confusing "pending FBR forever" limbo.

## 2. Terminal — non-fiscal receipt
`pos-terminal/electron/printer.ts` already omits the FBR block when `fbr_invoice_number`
is null, but prints `FBR_PENDING_NOTICE` ("FBR: pending…") in the else branch — wrong for
a non-fiscal resort.
- Add `is_fiscal?: boolean` to the receipt payload (`ReceiptInput`), defaulting to true so
  every existing FBR tenant is byte-for-byte unchanged.
- When `is_fiscal === false`: skip the FBR block **and** the pending notice; print a clean
  resort footer instead (e.g. "Thank you for visiting TDCP Kalar Kahar" + a thin rule).
  No "non-fiscal" legal stamp unless you want one — keep it looking like a normal hotel bill.
- The header already prints business name / branch / address / contact — perfect for a
  resort receipt. Show **room stay note** (guest name, check-in/out) when present.
- `pos-terminal/src/routes/payment.tsx`: pass `is_fiscal: tenant.fbr_connection_type !== "none"`
  into `window.api.printer.print({...})`.

## 3. Terminal — Rooms as a first-class category (the "one flexible till")
Per the three visitor types (restaurant-only / rooms-only / both), the till stays **one
cart**; the cashier adds room lines and/or food lines to a single invoice.
- **Rooms are products** in a top-level **"Rooms"** category (e.g. "Deluxe Room / night",
  "Standard Room / night", `uom = NIGHT`). No booking engine — **nights = quantity**
  (Deluxe ×3 = 3 nights). This is data + light UI, not a new subsystem.
- Make the Rooms category **prominent**: pin it first in the category bar (sort by a
  "Rooms"-first rule or `display_order`), with a distinct icon/color, so a rooms-only or
  combined guest reaches it in one tap. Restaurant menu categories follow.
- **Stay details as a note:** a small "Room details" affordance on a room line (or at
  checkout) to capture **guest name + check-in/check-out dates** → stored on the invoice
  (reuse `SaleItem.item_note` / invoice notes) and printed on the receipt. No date math.
- Restaurant flow (order type, table, modifiers, KOT) is **unchanged** and only shows for
  food items — a rooms-only sale simply never touches it.
- Gating: this Rooms prominence shows for the TDCP tenant (vertical `restaurant` +
  non-fiscal, or a small `has_rooms`/module check). Other tenants are unaffected.

## 4. Seed — TDCP Kalar Kahar demo tenant
New management command `backend/apps/tenants/management/commands/seed_tdcp_demo.py`
(mirrors the existing `seed_restaurant_demo.py`), idempotent:
- Tenant: business_name "TDCP — Kalar Kahar Resort", `business_mode="pos"`,
  `vertical="restaurant"`, `fbr_connection_type="none"`.
- Owner + cashier (PIN), one **Branch** "Kalar Kahar", one **Terminal** (prints a pairing
  code for the demo laptop).
- **Rooms** category + room products (Deluxe/Executive/Standard per night) — realistic
  TDCP-style placeholders.
- **Restaurant**: a few tables + a placeholder menu (categories + items + a modifier group)
  **to be replaced with TDCP's real menu** the moment you share it (re-running the command
  or a small `import_tdcp_menu` updates by SKU).
- No FBR token, no scenarios — nothing FBR.

## 5. Admin-web (light)
- Restaurant/menu + Rooms are managed via the existing **catalog** (categories/products)
  and **restaurant** (tables/modifiers) screens — no new admin build needed for the demo.
- Hide FBR-specific admin UI for non-fiscal tenants (reuse existing module/`RequireDiApi`
  gating keyed off `fbr_connection_type`), so managers don't see irrelevant FBR setup.

---

## Critical files
- Backend: `apps/tenants/business_mode.py`, `apps/fbr/tasks.py`, new
  `apps/tenants/management/commands/seed_tdcp_demo.py`.
- Terminal: `electron/printer.ts` (non-fiscal footer + `is_fiscal`),
  `src/routes/payment.tsx` (pass `is_fiscal`), Rooms category prominence in the
  sale/catalog UI (`src/routes/sale.tsx` + category bar), optional room-stay-note component.
- Reuse, don't rebuild: `features/restaurant/*`, pairing (`routes/pairing.tsx`), printing,
  `seed_restaurant_demo.py` as the template.

## Verification
- Backend: `manage.py check`; `makemigrations --check`; unit test that a non-fiscal
  tenant's invoice returns `{"skipped":"non_fiscal"}` and stays `fbr_invoice_number=NULL`.
- Terminal: run the app on the Mac/laptop against prod, **pair with the seeded code**
  (proves FBR-free connectivity), ring up (a) restaurant-only, (b) rooms-only ×N nights,
  (c) combined room+restaurant, and confirm each prints a clean **non-fiscal** receipt
  (no FBR logo/QR/number/pending) to PDF or a real thermal printer.
- Regression: an existing FBR tenant (e.g. PEER TRADERS) still prints the full FBR block
  and still submits — `is_fiscal` defaults true, `fbr_connection_type != none` unchanged.

## Out of scope (confirmed)
Booking/reservation/availability system, check-in/out workflow, guest folio across stays,
housekeeping/room status, FBR/PRA fiscalization. This is a plain resort POS for TDCP only.

## Pending from you
TDCP's **real restaurant menu** (and ideally the **room types + nightly rates** for Kalar
Kahar). I'll seed realistic placeholders now so the demo is fully clickable, and swap in
the real data as soon as you share it.
