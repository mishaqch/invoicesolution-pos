# Integrations — Pakistan POS

> Practical implementation details for every external system the POS talks to: the FBR Digital Invoicing platform via PRAL, every payment method (cash, card, EasyPaisa, JazzCash, Raast, bank transfer, store credit, cheque), and every hardware device (thermal printer, barcode scanner, cash drawer, customer display, weighing scale).

This document is the most "production-like" of the four. Read it alongside `DATABASE_SCHEMA.md` (for what to persist) and `SCREENS.md` (for the UI flows that drive these calls).

---

## Part 1 — FBR / PRAL Digital Invoicing

The complete lifecycle, from a fresh tenant signup to a stable production-grade submission stream.

### 1.1 The actors

- **Taxpayer** — our customer (the shop owner). They have a CNIC/NTN and an IRIS portal account.
- **PRAL** — Pakistan Revenue Automation. Operates the API.
- **Licensed Integrator (LI)** — the entity submitting invoices on behalf of taxpayers. **For us, this is PRAL itself**, free of cost. Other LIs may charge up to Rs. 10/invoice, Rs. 100k/month, or Rs. 1M/year — these are regulated ceilings.
- **Our central server** — sits in the middle. Holds whitelisted static IPs. All terminal traffic to PRAL flows through us.

### 1.2 The endpoints we care about (sandbox)

| Purpose | URL pattern | Method |
|---|---|---|
| Post invoice (sandbox) | `https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb` | POST |
| Validate invoice (sandbox, dry-run) | `https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata_sb` | POST |
| Post invoice (production) | `https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata` | POST |
| Validate invoice (production) | `https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata` | POST |

URLs above are pulled from the v1.6 manual; **always re-fetch the customer's specific URL from the IRIS portal — the manual notes it can be customer-specific.**

### 1.3 Authentication

Every request:
```http
POST /di_data/v1/di/postinvoicedata_sb HTTP/1.1
Host: gw.fbr.gov.pk
Authorization: Bearer <token>
Content-Type: application/json
```

Tokens are issued per environment (sandbox token + production token), per taxpayer. They're long-lived (no refresh flow documented). Store encrypted in `fbr_tokens.token_encrypted` using app-level encryption (Fernet with key from environment).

### 1.4 The invoice JSON shape

This is the wire format. Build it from our internal `Invoice` + `SaleItem` records via a single mapper module (`backend/apps/fbr/builder.py`).

```json
{
  "invoiceType": "Sale Invoice",
  "invoiceDate": "2026-05-08",
  "sellerNTNCNIC": "1234567",
  "sellerBusinessName": "Khalil General Store",
  "sellerProvince": "PUNJAB",
  "sellerAddress": "Plot 45, DHA Phase 5, Lahore",
  "buyerNTNCNIC": "0000000000000",
  "buyerBusinessName": "Walk-in Customer",
  "buyerProvince": "PUNJAB",
  "buyerAddress": "",
  "buyerRegistrationType": "Unregistered",
  "invoiceRefNo": "MAIN-T1-2026-0001234",
  "scenarioId": "SN001",
  "items": [
    {
      "hsCode": "1006.3010",
      "productDescription": "Basmati rice 5kg",
      "rate": "18%",
      "uoM": "Numbers, pieces, units",
      "quantity": 2,
      "totalValues": 2360,
      "valueSalesExcludingST": 2000,
      "fixedNotifiedValueOrRetailPrice": 0,
      "salesTaxApplicable": 360,
      "salesTaxWithheldAtSource": 0,
      "extraTax": 0,
      "furtherTax": 0,
      "sroScheduleNo": "",
      "fedPayable": 0,
      "discount": 0,
      "saleType": "Goods at standard rate (default)",
      "sroItemSerialNo": ""
    }
  ]
}
```

Critical field gotchas:

- `invoiceDate` is `yyyy-mm-dd` only, no time component.
- `rate` is a string like `"18%"`, not a number. Yes, really.
- `uoM` is a verbose enum string ("Numbers, pieces, units", "Kilograms", etc.) — keep a constant map.
- `totalValues` includes tax. `valueSalesExcludingST` is the pre-tax line subtotal.
- `salesTaxApplicable` is the rupee amount of sales tax on this line.
- `buyerRegistrationType` is one of `"Registered"` or `"Unregistered"`. For unregistered walk-ins, use `buyerNTNCNIC: "0000000000000"` (13 zeros) — confirmed acceptable by PRAL during sandbox testing.
- `scenarioId` is required only during sandbox testing. Omit or empty for production.
- All money fields are numbers in PKR (not paisa, not strings).

### 1.5 The response shape

Success:
```json
{
  "invoiceNumber": "8885801DIZMTQGA978020-21",
  "dated": "2026-05-08T14:23:11+05:00",
  "validationResponse": {
    "statusCode": "00",
    "status": "Valid",
    "invoiceStatuses": [
      { "itemSNo": "1", "statusCode": "00", "status": "Valid", "invoiceNo": null, "errorCode": null, "error": null }
    ]
  }
}
```

Failure:
```json
{
  "validationResponse": {
    "statusCode": "01",
    "status": "Invalid",
    "error": "",
    "invoiceStatuses": [
      {
        "itemSNo": "1",
        "statusCode": "01",
        "status": "Invalid",
        "invoiceNo": null,
        "errorCode": "0053",
        "error": "Provided Registration type does not match with Buyer's profile..."
      }
    ]
  }
}
```

`statusCode == "00"` means valid. Anything else = error. Persist the entire response in `fbr_submissions.response_payload`.

### 1.6 Onboarding flow (the wizard in Admin → FBR)

Walk the customer through:

**Step 1 — Confirm IRIS account.** Verify the tenant has logged in to IRIS at least once. We can't do this automatically; we ask them to confirm and link to the IRIS login page.

**Step 2 — Select integrator.** Two cards: "PRAL (free, recommended)" and "Other licensed integrator". Default to PRAL. If they pick another, show fee caps prominently.

**Step 3 — Business nature & sector.** Multi-select for natures (Manufacturer, Importer, Retailer, etc.) and single-select for sector (FMCG, Pharmaceuticals, etc., or "All Other Sectors" for multi-sector retailers). Save to `tenants.fbr_business_natures` and `fbr_sector`.

**Step 4 — Technical contact.** Form fields the customer fills, that we POST to the IRIS portal. They include name, email, phone, ERP/system provider (= our product name), software type (Cloud), software version, CRM email + password (for the PRAL CRM at dicrm.pral.com.pk).

**Step 5 — IP whitelisting.** We submit OUR static IPs (1–3) on their behalf. They confirm the hosting provider name and country (we pre-fill since it's our infra). PRAL accepts/rejects within 2 working hours.

**Step 6 — Sandbox token.** Once IPs are accepted, IRIS displays the sandbox token. The customer logs in to IRIS, copies the token, pastes it into our wizard. We encrypt and store. (V2: automated token retrieval if PRAL exposes it — not supported as of v1.6 of the manual.)

**Step 7 — Scenario testing.** Auto-generated test invoices for the customer's selected sector. We run them all, report green/red. On all-green, IRIS unlocks the production token.

**Step 8 — Production token.** Customer copies/pastes again. We encrypt and switch the tenant's environment from `sandbox` → `production`.

Document the entire flow on a single admin page. The customer should be able to start at 9 AM and have a working production setup by lunch.

### 1.7 Scenario testing

The customer's selected sector determines which scenarios apply (e.g., Pharmaceuticals → SN001, SN002, SN003; Mobile → SN001, SN015; etc.). The IRIS dashboard shows "Eligible scenarios" once technical details are submitted.

For each eligible scenario:

1. Build a synthetic invoice JSON matching the scenario description (e.g., SN001 = "Goods at standard rate to registered buyer").
2. POST to sandbox with `scenarioId: "SN001"`.
3. Capture response.
4. Update `fbr_scenario_tests` row.

Implementation: a service `backend/apps/fbr/scenario_runner.py` that holds a dict of scenario builders. Each builder takes the tenant context and returns a fully-formed JSON. Run them all in parallel via Celery group.

The catalog of scenarios will grow as PRAL adds more; design `scenario_builders` as a registry (`@register("SN015")`) so new scenarios are one-file additions.

### 1.8 Real-time submission flow (production)

Once the tenant is live:

1. Cashier completes a sale. POS writes invoice to local SQLite with `status='pending_sync'`.
2. POS sync worker POSTs to our `/api/sync/invoices/` endpoint with the invoice + `Idempotency-Key` header.
3. Our Django view validates inputs, persists to Postgres with `status='submitted'`, and enqueues a Celery task.
4. Celery task `submit_invoice_to_fbr(invoice_id)`:
   - Loads the invoice from Postgres.
   - Builds JSON via the mapper.
   - POSTs to `postinvoicedata` with the production token.
   - On success: updates `invoices.fbr_invoice_number`, `fbr_qr_payload`, `fbr_validated_at`, `status='valid'`. Writes a `fbr_submissions` row.
   - On failure: writes `fbr_submissions` with error, schedules retry with exponential backoff (10s, 30s, 2min, 10min, 1hr, 6hr). After 5 attempts, status → `failed` and surfaces to admin.
5. POS polls our API for status updates (every 30s or on-demand). Once it sees `valid`, it updates local SQLite and the receipt is reprinted with QR code (or printed for the first time, if the customer prefers FBR-confirmed receipts).

**Timeout discipline.** Every PRAL call has a 30-second hard timeout. Network slowness should never block our worker forever.

**Idempotency.** Our `/api/sync/invoices/` endpoint is idempotent on the `client_uuid` field. If the POS retries and we already have that UUID, we return the existing record's status without re-enqueueing.

### 1.9 The 72-hour edit window

Per the manual:

> Corrections must be made within 72 hours of issuing the invoice (Insertion Date). Invoices will be moved to return after 72 hours of invoice posting time or at month end, whichever comes first, and cannot be cancelled afterward.

Therefore `invoices.edit_deadline_at = MIN(insertion_date + 72h, last_day_of_month + 23:59:59)`.

Set this column at the moment FBR returns `valid`. Use it everywhere the UI says "editable" or "cancellable".

A scheduled Celery beat job runs hourly:
- Finds invoices where `edit_deadline_at < now()` and status ∈ `{valid, edited, partially_edited, partially_cancelled, partially_edited_and_cancelled}`.
- Transitions them to `finalized`. (No FBR call needed — this is purely our local lifecycle marker. PRAL has already moved them server-side.)

### 1.10 The 10% monthly cancel cap

Per the manual:

> Invoice cancellation is allowed only when its value does not exceed 10% of last month's sales. Once the limit is exhausted, no further invoices can be cancelled. The 10% limit is the total limit allowed for all invoice modification together.

This applies to **edits AND cancellations combined**. Implement:

**Monthly budget calculation** (Celery beat, runs at 00:05 on the 1st of each month):
```python
for tenant in active_tenants:
    last_month = previous_calendar_month(tenant.timezone)
    sales_total = Invoice.objects.filter(
        tenant=tenant,
        invoice_date__range=last_month,
        status__in=['valid', 'edited', 'partially_edited',
                    'cancelled', 'partially_cancelled',
                    'partially_edited_and_cancelled', 'finalized']
    ).aggregate(Sum('grand_total'))['grand_total__sum'] or 0
    
    FbrCancelBudget.objects.create(
        tenant=tenant,
        month_start=this_month_start,
        previous_month_sales=sales_total,
        budget_amount=sales_total * Decimal('0.10'),
        consumed_amount=0,
        remaining_amount=sales_total * Decimal('0.10'),
    )
```

**Consumption tracking** (synchronous, before any edit/cancel action):
```python
@transaction.atomic
def consume_cancel_budget(tenant, invoice, action_type):
    budget = FbrCancelBudget.objects.select_for_update().get(
        tenant=tenant, month_start=current_month_start
    )
    consumption_amount = invoice.grand_total
    if budget.remaining_amount < consumption_amount:
        raise CancelBudgetExceeded(
            f"Cancel budget exceeded. Remaining: Rs. {budget.remaining_amount}, "
            f"this action requires Rs. {consumption_amount}. "
            f"Use a credit note instead."
        )
    budget.consumed_amount += consumption_amount
    budget.remaining_amount -= consumption_amount
    budget.save()
    FbrCancelBudgetConsumption.objects.create(
        budget=budget, invoice=invoice,
        consumption_type=action_type, amount=consumption_amount,
        consumed_by=current_user(),
    )
```

**UI surfacing**:
- POS terminal: tiny indicator in the header showing remaining budget when it drops below 50%. Becomes prominent (amber) below 20%, red when zero.
- Admin → FBR → Cancel budget tracker shows the full picture.
- When remaining < value of attempted cancel: refuse with clear message + link to "Create credit note instead" flow.

### 1.11 The edit/cancel constraint matrix

From the manual:

| Action | Pre-condition |
|---|---|
| Edit invoice header | Never. Header is immutable. |
| Edit individual item | Within 72h, item not yet edited (max 1 edit per item ever) |
| Cancel individual item | Within 72h, item not yet edited |
| Cancel whole invoice | Within 72h, NO item has been edited yet |
| Edit invoice date | Allowed within 72h, but cannot go earlier than 3 days before today |
| Edit referenced via Annexure-C | Never |
| Edit if already in submitted return | Never |

Encode these as predicates in `backend/apps/fbr/rules.py`:

```python
def can_edit_item(invoice, item) -> tuple[bool, str | None]:
    if invoice.status == 'finalized':
        return False, "Invoice is already in submitted return"
    if now() > invoice.edit_deadline_at:
        return False, "72-hour edit window has passed"
    if item.is_cancelled:
        return False, "Item is already cancelled"
    if item.edit_count >= 1:
        return False, "Item has already been edited (max 1 edit allowed)"
    if invoice.is_annexure_c_linked:
        return False, "Invoices linked to Annexure-C cannot be edited"
    return True, None

def can_cancel_invoice(invoice) -> tuple[bool, str | None]:
    if invoice.status == 'finalized':
        return False, "Invoice is already finalized"
    if now() > invoice.edit_deadline_at:
        return False, "72-hour cancel window has passed"
    if any(item.is_edited for item in invoice.items.all()):
        return False, "Cannot cancel: at least one item has been edited"
    # ... budget check is separate (see 1.10)
    return True, None
```

These predicates are called both server-side (authoritative) and client-side (for UX disabling).

### 1.12 The QR code on receipts

The QR contains the FBR-returned data and is scannable by the FBR Tax Asaan mobile app for verification. Per the v1.6 manual, the QR contains the FBR Invoice Number plus a verification payload (PRAL hasn't published the exact spec; the v1.6 PDF shows the QR but doesn't define its content).

Practical approach for V1:
1. After successful submission, store `fbr_qr_payload` = `{"invoiceNumber": "...", "validatedAt": "...", "amount": ..., "sellerNTN": "..."}` (a JSON string).
2. Generate QR using `qrcode` Python lib server-side, return as base64 PNG to POS.
3. POS prints PNG via ESC/POS image command.

When PRAL publishes the official QR spec, swap the payload encoding and regenerate.

### 1.13 Failure handling — the four error categories

When PRAL returns `statusCode != "00"`, parse the error and route to one of:

| Category | Examples | Action |
|---|---|---|
| **Transient** (network, gateway 5xx, timeout) | "Server unavailable", connection refused | Retry with backoff (max 5 attempts) |
| **Data validation** | "Buyer NTN missing", "HS code invalid", "Tax mismatch" | Mark as `failed`, notify admin, do NOT retry — needs human fix |
| **Business rule** | "Edit window passed", "Cancel budget exceeded" | Mark as `failed` permanently, surface clear UI message |
| **Auth** | "Token expired", "401" | Mark token inactive, alert tenant to re-auth |

Map every PRAL error code we encounter to one of these categories in `fbr/error_mapping.py`. As we encounter new codes in production, add them.

### 1.14 PRAL CRM (support tickets)

For each tenant, the CRM credentials are captured during onboarding. We can submit support tickets programmatically — but for V1, we just give the customer a "Open ticket with PRAL" link to dicrm.pral.com.pk and let them handle it directly.

In V1.5, integrate: a "Report this to PRAL" button on failed submissions auto-files a CRM case.

---

## Part 2 — Payment methods

Pakistan's payment landscape is a mix of cash, plastic, mobile wallets, and the new Raast rail. Each has its own integration pattern. **For V1, focus on doing each one CORRECTLY**, even if it means manual reference entry — automation comes later.

### 2.1 Cash

**The most common method. Get this perfect first.**

**Flow**:
1. Cashier selects "Cash" in payment screen.
2. Numeric input pre-filled with remaining amount due.
3. Cashier enters tendered amount (or uses quick-pick: 100, 500, 1000, 5000).
4. System computes change due.
5. Cashier confirms → POS records payment with method='cash' → triggers cash drawer open command (see 3.3) → prints receipt.

**Edge cases**:
- Tendered < remaining: error, ask for more.
- Tendered = remaining: no change, normal completion.
- Tendered > remaining: change due displayed prominently. Cashier hands change physically.
- Multi-tender: cash can fund part of a sale; another method funds the rest.

**Animation**: change-due number animates with green flash if positive. If exact (no change), shows a small "Exact" pill.

**Storage**: `payments` row with `payment_method='cash'`, `amount=<tendered_minus_change>` (the actual cash kept). The `change_given` field on `invoices` records the change handed back.

### 2.2 Card (debit / credit)

**Pakistan reality**: card payments go through a separate physical POS terminal (1Link, NIFT, BankIslami, etc.) provided by the customer's bank. Our POS does NOT integrate with the card network directly — that would require PCI-DSS certification, an MID per merchant, and acquirer relationships. **Out of scope for V1.**

Our role: **record the result of the card transaction** so the books reconcile.

**Flow**:
1. Cashier selects "Card" → "Credit" or "Debit".
2. Cashier swipes/inserts card on the bank's terminal, enters PIN, etc. (separate device, separate flow).
3. Bank terminal prints a slip with: last-4 of card, auth code, RRN (retrieval reference number), amount.
4. Cashier types into our POS:
   - Last-4 of card.
   - Auth code (6-digit).
   - RRN (12-digit, optional but recommended for reconciliation).
   - Amount (pre-filled, editable).
5. Our POS records the payment.

**UI**:
- Three numeric input fields, each labeled clearly.
- Auto-focus moves between fields.
- Last-4 validates as 4 digits.
- Auth code validates as 6 digits.
- "Skip RRN" link if cashier doesn't have it.

**Storage**: `payments` row with `payment_method` ∈ `{card_credit, card_debit}`, `card_last4`, `card_auth_code`, `card_rrn`. Bank terminal slip is stapled to the cashier's day-close report; we don't capture an image.

**V1.5 — automated reconciliation**: many Pakistani banks email a daily settlement report. Build a Celery task that ingests these and matches to our `payments` table, flagging discrepancies. This is HUGE value-add but not required for V1.

**V2 — direct integration**: explore 1Link's POS-to-POS API once the merchant base is large enough to negotiate. Saves the cashier from typing.

### 2.3 EasyPaisa

EasyPaisa (Telenor Microfinance Bank) supports multiple merchant integration modes. Three relevant to us:

#### 2.3.1 Static merchant QR (V1 default)

Easiest. Customer's existing EasyPaisa merchant QR sticker is mounted at the counter. Customer scans → enters amount → pays. Cashier marks our POS as paid after customer shows the success screen.

**Flow**:
1. Cashier selects "EasyPaisa".
2. POS shows: "Have customer scan the QR at the counter." Or shows a digital copy of the merchant's QR full-screen on customer-facing display.
3. Customer pays via their app.
4. Customer shows success screen / says "transaction ID 12345xxxx".
5. Cashier enters transaction ID into POS, confirms.

**Storage**: `payments` row with `payment_method='easypaisa'`, `wallet_provider='easypaisa'`, `wallet_phone` (optional, customer's number), `wallet_transaction_id`.

**Risk**: cashier could mark paid without verification. Mitigate: train shopkeepers, and integrate the merchant API (next) when feasible.

#### 2.3.2 EasyPaisa Merchant API (V1.5)

EasyPaisa offers a "One Link" / Merchant Services API for verified merchants. Onboarding requires:

- Merchant agreement with EasyPaisa.
- API credentials (HMAC + merchant ID).
- IP whitelisting on EasyPaisa side (we use the same static IPs as PRAL).

**Flow**:
1. Cashier selects "EasyPaisa".
2. Our backend calls EasyPaisa MA-Initiate API with amount, merchant ID, transaction ID.
3. EasyPaisa returns a transaction reference.
4. Customer-facing display shows a dynamic QR with this reference.
5. Customer scans, authorizes in their app.
6. EasyPaisa fires a webhook to our `/api/payments/easypaisa/webhook/` endpoint with success/failure.
7. POS, polling our backend, sees the status update and auto-completes the sale.

**Storage**: same as 2.3.1 but with verified `wallet_transaction_id` (tamper-proof).

#### 2.3.3 EasyPaisa Direct Debit (V2)

Customer enters their EasyPaisa-registered phone in our POS, gets an OTP on their phone, enters it. Money debits directly. Best UX but most complex onboarding.

### 2.4 JazzCash

Same architecture as EasyPaisa. JazzCash (Mobilink Microfinance Bank) has a similar API surface.

**V1**: static merchant QR + manual reference entry.
**V1.5**: Merchant API integration.

`payment_method='jazzcash'`, fields identical to EasyPaisa.

**Implementation note**: build a generic `wallet_payment` adapter pattern — both EasyPaisa and JazzCash plug in as different providers. This makes adding NayaPay, SadaPay, UPaisa, etc. easy in V2.

### 2.5 Raast

Raast is the State Bank of Pakistan's instant payment system. Two consumer-facing modes:

- **P2P (person-to-person)**: account-to-account by phone number / IBAN. Free for consumers.
- **P2M (person-to-merchant)**: customer pays a merchant via QR. **This is what we want.**

**Why Raast matters**: lowest fees of any digital method (often free or near-free for merchants), settlement is INSTANT, and SBP is mandating banks to support it. Volume is growing fast.

**Flow** (V1, static QR):
1. Merchant has a Raast QR sticker (provided by their bank).
2. Cashier selects "Raast".
3. POS shows the static QR or displays it on customer-facing display.
4. Customer scans with any banking app, enters amount, pays.
5. Bank credits the merchant in seconds.
6. Cashier enters reference number from customer's app to confirm.

**Flow** (V1.5, dynamic QR via bank's Raast aggregator):
1. Cashier selects "Raast".
2. Our backend calls the merchant's bank's Raast API to generate a dynamic QR with amount embedded.
3. QR shown on customer display.
4. Customer scans → confirms (no amount entry needed) → pays.
5. Webhook to our backend, auto-completes sale.

**Storage**: `payment_method='raast'`, `raast_iban` (merchant's IBAN that received), `raast_transaction_id`.

**Pricing leverage**: in marketing, emphasize Raast as "the cheapest way to accept digital payments". This is a real advantage for our customers.

### 2.6 Bank transfer

For B2B sales or large-ticket items where wallet limits don't fit.

**Flow**:
1. Cashier selects "Bank transfer".
2. POS shows our customer's bank account details on customer display.
3. Customer transfers from their bank app (IBFT or Raast).
4. Cashier enters reference number when customer confirms.

**Storage**: `payment_method='bank_transfer'`, `bank_name`, `bank_account_last4`, `bank_reference`.

### 2.7 Cheque

Less common in retail, but used for B2B.

**Flow**:
1. Customer hands cheque.
2. Cashier records cheque number, bank, date, amount in POS.
3. Sale recorded as paid (status `cheque_status='pending'`).
4. Manager reconciles cheque clearance later — updates `cheque_status='cleared'` or `'bounced'`. Bounced cheques flag the customer's account.

**Storage**: `payment_method='cheque'`, `cheque_number`, `cheque_date`, `cheque_status`.

**UI flag**: invoices paid by uncleared cheque are visually marked differently in admin lists.

### 2.8 Store credit / wallet

Customer has a balance on file (from past returns, deposits, or loyalty).

**Flow**:
1. Customer must be selected on the sale.
2. Cashier picks "Store credit" — only enabled if customer has positive `customers.store_credit`.
3. POS deducts up to `min(remaining, store_credit)`.
4. Cashier confirms.

**Storage**: `payment_method='store_credit'`, debits `customers.store_credit` and writes a `customer_ledger` row.

### 2.9 Split payment

Multiple payment methods on one invoice. Examples:
- Cash 1500 + EasyPaisa 500
- Card 8000 + Cash 200 (customer didn't have full amount on card)
- Store credit 1000 + Card 4000

**UI**: each tender appears in a list as the cashier adds it. Remaining decreases. Until remaining = 0, "Complete sale" stays disabled. If a tender needs to be removed, click ✗ on the tender row.

**Constraint**: ALL the tenders for one invoice must be settled before completion. We don't allow "I'll pay the rest tomorrow" — that's a credit sale, see 2.10.

### 2.10 Credit sales (customer pays later)

For trusted customers: invoice now, pay later.

**Flow**:
1. Customer selected (mandatory).
2. Cashier picks "Credit" as payment method (only if customer has `credit_limit > 0` or owner overrides).
3. Sale completes with `paid_total = 0`, customer's `current_balance` increases.
4. Later, customer comes to settle. Cashier opens customer profile → "Receive payment" → records cash/wallet/card → applies to oldest open invoices.

**UI for credit limit**: if sale would exceed customer's credit limit, blocks unless owner PIN.

---

## Part 3 — Hardware

What we plug into the POS terminal and how we drive it.

### 3.1 Thermal printer

The single most important piece of hardware. Cashier rings up nothing if the printer doesn't work.

**Supported models**: any ESC/POS-compatible thermal printer. Tested specifically:
- Epson TM-T20III (80mm, USB) — gold standard, ~Rs. 25,000.
- HOIN HOP-H58 (58mm, USB/Bluetooth) — budget, ~Rs. 6,500. Common in small shops.
- Xprinter XP-T80B (80mm, USB/LAN) — mid-range, ~Rs. 15,000.

**Connection**: USB (most common), Ethernet (network printers), or Bluetooth (tablets, less common). Our Electron app must support all three.

**Library**: `node-thermal-printer`. Wraps ESC/POS commands cleanly:

```typescript
import { ThermalPrinter, PrinterTypes } from 'node-thermal-printer';

const printer = new ThermalPrinter({
  type: PrinterTypes.EPSON,
  interface: 'printer:POS-80', // or 'tcp://192.168.1.100' or 'usb'
  characterSet: 'PC1252_MULTILINGUAL_LATIN1',
  width: 48, // 80mm = 48 chars; 58mm = 32 chars
});

printer.alignCenter();
printer.bold(true);
printer.println(tenant.business_name);
printer.bold(false);
printer.println(branch.address);
printer.println(`NTN: ${tenant.ntn}`);
printer.drawLine();

// items
for (const item of invoice.items) {
  printer.tableCustom([
    { text: item.product_name, width: 0.55 },
    { text: `${item.quantity} × ${item.unit_price}`, width: 0.25, align: 'RIGHT' },
    { text: item.line_total.toFixed(2), width: 0.20, align: 'RIGHT' },
  ]);
}

printer.drawLine();
printer.alignRight();
printer.println(`Subtotal: Rs. ${invoice.subtotal}`);
printer.println(`Tax: Rs. ${invoice.tax_total}`);
printer.bold(true);
printer.setTextSize(1, 1); // 2x normal
printer.println(`Total: Rs. ${invoice.grand_total}`);
printer.setTextSize(0, 0);
printer.bold(false);

if (invoice.fbr_invoice_number) {
  printer.alignCenter();
  printer.println('FBR Digital Invoice');
  printer.println(invoice.fbr_invoice_number);
  await printer.printQR(invoice.fbr_qr_payload, { cellSize: 6 });
}

printer.cut();
await printer.execute();
```

**Receipt template**: the layout above is a starting point. Per-tenant customization (header, footer, logo) lives in `tenant_settings`. Logo is uploaded as PNG, converted to bitmap, sent via ESC/POS image command.

**Urdu text**: thermal printers handle Latin-1 natively; for Urdu, render the line to a small bitmap server-side (PIL with Noto Nastaliq Urdu font) and print as image. Slower (~500ms extra) but reliable. Per-line selective bitmap rendering keeps performance acceptable.

**Error handling**: every print call has a 5s timeout. On failure, surface a non-blocking toast: "Receipt failed to print. Reprint?" Cashier never blocked. Persistent failures logged for diagnostic.

**Reprint**: any past invoice can be reprinted from sales history. POS terminal stores last-N receipt bitmaps locally for instant reprint without rebuilding.

### 3.2 Barcode scanner

**Approach**: USB HID. Scanners emulate keyboards. No driver needed. They type the barcode + a configured suffix (usually Enter or Tab).

**Configuration**:
- Configure scanner to send Enter as suffix (one-time, via scanner's manual config barcodes).
- POS sale screen has the search input always focused when not in a modal.
- Scanner types barcode + Enter → search auto-fires → product added.

**Tested models**:
- Honeywell Voyager 1250g — workhorse, ~Rs. 8,000.
- Symbol LS2208 — older, dirt cheap (~Rs. 4,000), 1D only.
- Generic Chinese 2D scanners — Rs. 2,000–3,000, hit-and-miss quality.

**Fallback**: typed manual barcode entry. Search input accepts both barcode and product name.

**No library required** — Electron's renderer process handles HID input as keyboard events natively.

### 3.3 Cash drawer

**Connection**: Cash drawers use an RJ11/RJ12 jack. They don't connect to the computer directly — they connect to the **printer** via the printer's "drawer kick" port. Triggered by an ESC/POS command sent to the printer.

```typescript
// Trigger drawer via printer
printer.openCashDrawer(); // sends ESC p 0 25 250 sequence
await printer.execute();
```

**Tested**:
- Most Epson and Xprinter thermal printers have RJ11 drawer ports.
- Drawer brand is largely irrelevant — they're all 12V or 24V triggered. Match voltage to printer's port spec.

**Behavior**: drawer opens automatically on cash payments. Configurable: also open on no-sale ("manager wants to make change") via a button in the cashier menu.

**No-sale event**: opening the drawer without a sale is logged in `audit_log` with reason. Frequent unexplained no-sales is a fraud signal.

### 3.4 Customer-facing display

A second monitor (or tablet on a stand) showing the customer what's being charged.

**Approach**: Electron's `BrowserWindow` API supports multiple windows. We open a second window on the secondary display:

```typescript
const displays = screen.getAllDisplays();
const customerDisplay = displays.find(d => d.id !== screen.getPrimaryDisplay().id);

if (customerDisplay) {
  const customerWindow = new BrowserWindow({
    x: customerDisplay.bounds.x,
    y: customerDisplay.bounds.y,
    fullscreen: true,
    webPreferences: { ... },
  });
  customerWindow.loadURL('app://./customer-display.html');
}
```

**Communication**: the cashier's main window broadcasts state to the customer window via Electron IPC (current cart, totals, payment status).

**Hardware**: any HDMI/VGA monitor works. Cheap 15" LCD, ~Rs. 8,000. Some shops use a tablet.

**Fallback**: if no second display, this feature simply doesn't activate — controlled by `terminals.customer_display_enabled`.

### 3.5 Weighing scale (V1.5)

For groceries, butchers, fruit stalls.

**Connection**: serial (RS-232) or USB-serial. Scales output weight as ASCII like `ST,GS,+002.450 kg\r\n`.

**Library**: `serialport` (Node).

**Flow**:
1. Cashier selects a "weighable" product.
2. POS prompts for weight.
3. Cashier places item on scale, presses "Read".
4. POS reads serial port, parses weight, fills quantity field.
5. Sale continues normally.

**Tested**:
- Avery Weigh-Tronix scales.
- Aclas LS-series.
- Generic Chinese USB scales (often unreliable; test before recommending).

**V1 fallback**: cashier reads weight off the scale's display and types it in. Manual but works.

### 3.6 Fingerprint reader (V2)

For cashier login without PIN. Requires per-machine vendor SDK (DigitalPersona, Suprema, etc.). Out of V1 scope.

### 3.7 Receipt printer paper

Practical operational note for customer support:

- 80mm thermal paper rolls: ~Rs. 80 per roll, ~150 receipts per roll.
- 58mm rolls: ~Rs. 50 per roll, ~80 receipts per roll.
- Recommend customers buy in boxes of 50 from local distributors.
- Heat-sensitive: don't store rolls in hot cars (paper darkens, becomes unprintable).

### 3.8 Hardware certification matrix

For each new model a customer wants to use, run through this checklist:

- [ ] Connects to Electron POS app on first run.
- [ ] Prints test receipt with Latin and Urdu lines.
- [ ] Prints QR code without distortion.
- [ ] Cuts paper cleanly.
- [ ] Triggers cash drawer.
- [ ] Recovers from paper-out condition without manual intervention.
- [ ] Reprint after 60s idle still works.
- [ ] Network printer survives network blip.

Document each tested model in a "Compatible hardware" page in the admin area for sales/support reference.

---

## Part 4 — Cross-cutting concerns

Some integration concerns that span multiple modules.

### 4.1 Idempotency end-to-end

Every external call (PRAL, EasyPaisa webhook, payment confirmation) carries a client-generated UUID. Receiving system de-dupes on UUID. This makes retries safe across the entire chain: POS → our server → external.

### 4.2 Webhooks (incoming)

When external services (EasyPaisa, JazzCash, Raast aggregator) want to notify us of payment status, they hit our webhook URLs.

Design rules:
- Always verify HMAC signature.
- Always idempotent (same webhook fired twice = no double-effect).
- Always respond 200 quickly (within 2s); enqueue actual work to Celery.
- Persist raw webhook body for audit.

### 4.3 Time and timezone

PRAL operates in PKT (UTC+5). Our DB stores everything in UTC (`TIMESTAMPTZ`). All UI displays in tenant's local time (defaults to PKT).

Date-bounded operations (the 72-hour window, monthly cancel budget):
- "72 hours" is calculated as exactly 72 hours of wall-clock time.
- "Month-end" is calendar month-end in PKT.
- "Last month's sales" is the previous calendar month in PKT.

Always double-check timezone in tests. Bugs here cause real money mistakes.

### 4.4 Money math

Never use floats. Python `Decimal` everywhere. JS `BigInt` or store as integer paisa. Tax rounding: round per-line to 4 decimal places, then sum. Display rounding: 2 decimal places. Match what PRAL does.

### 4.5 Reconciliation

Daily Celery beat job at 02:00:
- Compare local invoice totals to FBR-acknowledged totals.
- Compare expected payment-method splits against external system reports (when API access available).
- Report discrepancies to admin dashboard.

If our books and reality drift, we want to know within 24 hours.

### 4.6 Disaster recovery for FBR

Scenario: PRAL is down for 6 hours. What happens?

- Sales continue. Local SQLite captures everything.
- Sync queue accumulates `pending_sync` invoices.
- When PRAL comes back: queue drains in priority order (oldest first).
- If queue depth >100 invoices, alert admin proactively.

Scenario: a tenant's production token is revoked by FBR.

- We start receiving 401s on submission.
- Mark token inactive, halt submissions for that tenant.
- Notify tenant: "Your FBR token is no longer valid. Please re-authenticate via IRIS and provide a new token."
- Sales continue offline-only; sync resumes once new token provided.

### 4.7 Compliance & documentation

For each integration we maintain in version control:
- API documentation (PDF/markdown of vendor's docs at the version we integrated against).
- Sample requests + responses (real ones, with PII redacted).
- Error code mappings.
- Test fixtures.

When PRAL releases a new manual version (currently 1.6), we diff it against our integration assumptions and file issues for any breaking changes.

---

*Integration health is monitored on a single admin dashboard widget: "External services status" — green dots for healthy, yellow for slow, red for down. Refreshed every 60 seconds.*
