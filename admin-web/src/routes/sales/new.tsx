import { AlertTriangle, FileText, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomerPicker } from "@/components/ui/customer-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { Select } from "@/components/ui/select";
import { InvoicePreview } from "@/features/invoices/InvoicePreview";
import { useModules } from "@/features/modules/hooks";
import { ApiError } from "@/lib/api";
import {
  useBranches,
  useCreateManualInvoice,
  useCustomers,
  useProducts,
  useStockLevels,
  useTaxRates,
  useTerminals,
  useUoms,
  useWarehouses,
  type ManualInvoiceLine,
  type ManualInvoicePayment,
} from "@/lib/queries";
import { priceInput, roundWhole } from "@/lib/utils";

// UUID v4 shape. Used to detect when `product.tax_rate` is the FK row
// id (current backend serializer behaviour) instead of the numeric
// percentage. When it matches, we look the rate up via useTaxRates.
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface DraftLine {
  product_id: string;
  product_name: string;
  product_sku: string;
  hs_code: string;
  uom_code: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  is_taxable: boolean;
  discount_amount: string;
}

// PRA (Punjab) restaurant rule: services paid by CARD get a reduced sales-tax
// rate; cash/other pays the standard rate. These are the two services rates.
const SERVICES_STANDARD_RATE = "16";
const SERVICES_CARD_REDUCED_RATE = "8";
const CARD_METHODS = new Set(["card_credit", "card_debit"]);
// An HS code in chapter 98 is a services line (matches the backend rule).
const isServicesHs = (hs: string) => (hs || "").trim().startsWith("98");

const PAYMENT_METHODS: ManualInvoicePayment["payment_method"][] = [
  "cash", "card_credit", "card_debit", "easypaisa", "jazzcash", "raast",
  "cheque", "bank_transfer", "store_credit",
];

function rs(amount: number | string): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  return `Rs. ${n.toLocaleString("en-PK", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function uuidv4(): string {
  // RFC4122-ish v4 — fine for client_uuid (server validates uniqueness).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Standalone invoice creation for non-POS workflows: wholesalers,
 * service providers, manual office entries. Builds a cart, computes
 * totals client-side for live feedback, posts to /api/sales/invoices/manual/
 * which atomically creates the invoice and queues the FBR submission.
 *
 * Mirrors the PRAL screens for invoice creation: invoice header (buyer +
 * seller branch), per-line item editor with HS code / UoM / rate / qty,
 * tax rollup, payment method.
 */
interface DebitNoteContext {
  invoiceType: "debit_note" | "credit_note";
  referenceInvoiceId: string;
  referenceInvoiceNumber: string;
  buyerName: string | null;
  buyerNtnCnic: string | null;
}

export default function NewInvoiceRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const branches = useBranches();
  const terminals = useTerminals();
  const warehouses = useWarehouses();
  const customers = useCustomers();
  const taxRates = useTaxRates();
  const uoms = useUoms();
  const create = useCreateManualInvoice();

  // FBR units for the per-line UoM dropdown: one option per distinct FBR unit,
  // full FBR name, "Numbers, pieces, units" pinned first. Same logic as the
  // product form so the unit shown here is exactly what FBR receives.
  const uomOptions = useMemo(() => {
    const seen = new Map<string, { code: string; label: string }>();
    for (const u of uoms.data ?? []) {
      const fbr = u.fbr_uom || u.name_en;
      const label = u.fbr_uom_label || fbr;
      if (!seen.has(fbr)) seen.set(fbr, { code: u.code, label });
    }
    const PCS = "Numbers, pieces, units";
    return Array.from(seen.values()).sort((a, b) => {
      if (a.label === PCS) return -1;
      if (b.label === PCS) return 1;
      return a.label.localeCompare(b.label);
    });
  }, [uoms.data]);
  const codeToOptionCode = useMemo(() => {
    const rows = uoms.data ?? [];
    const fbrByCode = new Map(rows.map((u) => [u.code, u.fbr_uom || u.name_en]));
    const repByFbr = new Map<string, string>();
    for (const u of rows) {
      const fbr = u.fbr_uom || u.name_en;
      if (!repByFbr.has(fbr)) repByFbr.set(fbr, u.code);
    }
    const m = new Map<string, string>();
    for (const u of rows) {
      const fbr = fbrByCode.get(u.code);
      const rep = fbr ? repByFbr.get(fbr) : undefined;
      if (rep) m.set(u.code, rep);
    }
    return m;
  }, [uoms.data]);

  // The product API returns `tax_rate` as the TaxRate row's UUID (FK),
  // but the invoice serializer expects a numeric percentage like "18".
  // Maintain a lookup so we can swap UUID → percentage whenever we
  // build a cart line. Falls back to "0" when no rate is selected
  // (non-taxable products). Wrapped in useMemo so we don't rebuild it
  // on every render.
  const taxRateByIdMemo = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of taxRates.data?.results ?? []) m.set(r.id, r.rate);
    return m;
  }, [taxRates.data]);

  function resolveTaxRate(raw: string | null | undefined): string {
    // Non-taxable / blank → 0 (DRF DecimalField accepts "0").
    if (!raw) return "0";
    // Already numeric (legacy / future shape)?  Pass through.
    if (!UUID_RE.test(raw)) return raw;
    // It's a UUID; look up the row's `rate` and use that.
    return taxRateByIdMemo.get(raw) ?? "0";
  }

  // Two tenant shapes for invoice creation:
  //   A) Multi-branch / multi-terminal tenants — pickers show, user
  //      chooses where the invoice is recorded.
  //   B) Office-invoice tenants without branches/terminals modules —
  //      no pickers; server auto-uses an implicit default pair.
  // The form sends branch/terminal UUIDs only when modules are enabled
  // AND values have been selected. Server-side fallback handles Shape B.
  const { data: modules } = useModules();
  // Digital-Invoicing-only tenants are back-office — they raise a tax invoice
  // to FBR without recording a till payment. Hide the Payments card for them
  // and submit the invoice with no payments (unpaid / on account). POS + Both
  // keep the Payments card.
  const isDigitalOnly = modules?.business_mode === "digital_invoicing";
  const showBranchPicker = modules
    ? modules.enabled.includes("branches")
    : true;
  const showTerminalPicker = modules
    ? modules.enabled.includes("terminals")
    : true;
  const showCustomerPicker = modules
    ? modules.enabled.includes("customers")
    : true;

  // Debit-note flow: invoice-detail page passes these via Link state when
  // the user clicks "Add debit note". The reference_invoice + invoice_type
  // fields end up on the POST body; the customer picker is disabled (buyer
  // copies from the original at the server).
  const debitContext = (location.state as { debitNote?: DebitNoteContext } | null)
    ?.debitNote ?? null;

  const [branchId, setBranchId] = useState("");
  const [terminalId, setTerminalId] = useState("");
  // Warehouse to deduct stock from (Digital Invoicing). Shown only when the
  // tenant has warehouses; defaults to the default warehouse.
  const [warehouseId, setWarehouseId] = useState("");
  const [customerId, setCustomerId] = useState("");
  // The picked customer object — the searchable CustomerPicker may not have the
  // selection in its current (search-scoped) results, so we keep the full object
  // here for the preview + button label.
  const [selectedCustomerObj, setSelectedCustomerObj] = useState<import("@/lib/queries").AdminCustomer | null>(null);
  const [notes, setNotes] = useState("");
  // Cart-level discount — applies on top of any per-line discounts.
  // `cartDiscountMode` controls how the input is interpreted:
  //   - "pct"  → operator types e.g. "10" → 10% off the (post-line-discount)
  //               subtotal. Stored verbatim and sent as cart_discount_pct.
  //   - "rs"   → operator types a flat Rs amount; we convert to the
  //               equivalent percent at submit time, because the server
  //               accepts cart_discount_pct only (max 5 digits, 2 dp).
  //               Conversion = (rs / pre-discount-subtotal) * 100, capped
  //               to 100 to avoid negative grand totals.
  const [cartDiscountInput, setCartDiscountInput] = useState("0");
  const [cartDiscountMode, setCartDiscountMode] = useState<"pct" | "rs">("pct");
  const [productSearch, setProductSearch] = useState("");
  const [showProductPicker, setShowProductPicker] = useState(false);
  const products = useProducts(productSearch.trim() ? { search: productSearch.trim() } : {});
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [payments, setPayments] = useState<ManualInvoicePayment[]>([
    { payment_method: "cash", amount: "0" },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [autoRateNote, setAutoRateNote] = useState<string | null>(null);

  const clientUuidRef = useRef<string>(uuidv4());

  // PRA card-payment reduced rate: when EVERY payment is a card (credit/debit),
  // services lines (HS chapter 98) get the reduced services rate (8%); when the
  // payment is not card-only, they revert to the standard rate (16%). This
  // recomputes the line rate + a visible note whenever payments or lines change.
  // Only touches services lines whose rate is currently one of the two services
  // rates — never clobbers a rate the operator set deliberately to something
  // else, and never touches goods lines.
  const paymentMethodsKey = payments.map((p) => p.payment_method).join(",");
  useEffect(() => {
    const servicesLines = lines.filter((l) => isServicesHs(l.hs_code));
    if (servicesLines.length === 0) { setAutoRateNote(null); return; }
    const hasPayment = payments.length > 0;
    const allCard = hasPayment && payments.every((p) => CARD_METHODS.has(p.payment_method));
    const target = allCard ? SERVICES_CARD_REDUCED_RATE : SERVICES_STANDARD_RATE;
    const swappable = new Set([SERVICES_STANDARD_RATE, SERVICES_CARD_REDUCED_RATE]);

    let changed = false;
    const next = lines.map((l) => {
      if (!isServicesHs(l.hs_code)) return l;
      if (!swappable.has(String(l.tax_rate))) return l; // operator set a custom rate — leave it
      if (String(l.tax_rate) === target) return l;
      changed = true;
      return { ...l, tax_rate: target };
    });
    if (changed) setLines(next);
    setAutoRateNote(
      allCard
        ? `Card payment: services taxed at the reduced ${SERVICES_CARD_REDUCED_RATE}% (PRA card rate).`
        : `Standard ${SERVICES_STANDARD_RATE}% services rate applied. Pay by card to use the reduced ${SERVICES_CARD_REDUCED_RATE}% rate.`,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paymentMethodsKey, lines.length, lines.map((l) => l.hs_code).join(",")]);

  // Pre-pick the first branch once available.
  useEffect(() => {
    if (!branchId && branches.data?.results?.[0]) {
      setBranchId(branches.data.results[0].id);
    }
  }, [branches.data, branchId]);

  // Keep the terminal consistent with the selected branch. A terminal can only
  // sell under its OWN branch (the server enforces this), so the terminal MUST
  // belong to `branchId`. When the branch changes — or on first load — pick the
  // first terminal in that branch; if the current terminal isn't in the branch,
  // replace it. (The old code pre-picked the GLOBAL first terminal independent
  // of the branch, which mismatched for multi-branch tenants like PEER TRADERS.)
  useEffect(() => {
    const all = terminals.data?.results ?? [];
    if (all.length === 0) return;
    // Terminals in the selected branch (or all, if no branch chosen yet).
    const inBranch = branchId ? all.filter((t) => t.branch === branchId) : all;
    const current = all.find((t) => t.id === terminalId);
    const currentInBranch = current && (!branchId || current.branch === branchId);
    if (!currentInBranch) {
      setTerminalId(inBranch[0]?.id ?? "");
    }
  }, [terminals.data, branchId, terminalId]);

  // Warehouses for the (possibly implicit) invoice branch. When the tenant has
  // no explicit branch picker, the implicit branch's warehouses still show —
  // we filter by branchId only when a branch is actually selected.
  const allWarehouses = warehouses.data?.results ?? [];
  const branchWarehouses = branchId
    ? allWarehouses.filter((w) => w.branch === branchId)
    : allWarehouses;
  const showWarehousePicker = branchWarehouses.length > 0;

  // Default to the branch's default warehouse (else its first), re-running when
  // the branch changes or warehouses load.
  useEffect(() => {
    if (!showWarehousePicker) return;
    const stillValid = branchWarehouses.some((w) => w.id === warehouseId);
    if (!stillValid) {
      const def = branchWarehouses.find((w) => w.is_default) ?? branchWarehouses[0];
      setWarehouseId(def?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [branchId, warehouses.data]);

  // On-hand availability for the line being invoiced. Scope it to the warehouse
  // the sale deducts from (Digital Invoicing) or, failing that, the branch (POS)
  // — exactly what the server will draw down. We only warn (never block): a real
  // shop's count can lag reality, so the operator decides. Wholesale/office
  // tenants with no stock rows simply see no availability column.
  const stockScope: Record<string, string> = warehouseId
    ? { warehouse: warehouseId }
    : branchId
      ? { branch: branchId }
      : {};
  const stockLevels = useStockLevels(stockScope);
  const onHandByProduct = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of stockLevels.data?.results ?? []) {
      // Sum across variants of the same product so the line-level number is the
      // product's total on-hand at this location.
      m.set(s.product, (m.get(s.product) ?? 0) + Number(s.quantity || "0"));
    }
    return m;
  }, [stockLevels.data]);

  // Whether the availability column is meaningful (the tenant actually tracks
  // stock at this location). Office/wholesale tenants with no rows → hidden.
  const tracksStock = (stockLevels.data?.results.length ?? 0) > 0;

  // Track whether the single payment amount has been edited manually.
  // While untouched (or matching the previous auto-fill), keep the
  // amount synced to the grand total. Once split-tender (>1 row) the
  // sync stops — multiple payments need manual amounts.
  const [paymentAutoFilled, setPaymentAutoFilled] = useState(true);

  // The cart-level discount as a percent (0–100). Derived in one spot
  // so the totals memo + the submit() payload + the InvoicePreview all
  // agree on the same number.
  const cartDiscountPct = useMemo(() => {
    const raw = Number(cartDiscountInput) || 0;
    if (raw <= 0) return 0;
    if (cartDiscountMode === "pct") {
      return Math.min(100, raw);
    }
    // "rs" mode: convert flat Rs → percent of post-line-discount subtotal.
    // We need the line-level subtotal here, so compute it inline.
    let sub = 0;
    for (const line of lines) {
      const qty = Number(line.quantity) || 0;
      const price = Number(line.unit_price) || 0;
      const lineDiscount = Number(line.discount_amount) || 0;
      sub += Math.max(0, qty * price - lineDiscount);
    }
    if (sub <= 0) return 0;
    return Math.min(100, (raw / sub) * 100);
  }, [cartDiscountInput, cartDiscountMode, lines]);

  // Live totals — recompute on every cart edit. Mirrors the POS
  // pricing engine's logic at the line-level (qty * unit_price -
  // discount, tax = (line_net) * rate%), then applies the cart-level
  // discount on top — prorated across lines (each line's net shrinks
  // by `cartDiscountPct`), which keeps the per-line tax band breakdown
  // mathematically consistent with what the server computes.
  const totals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    let lineDiscount = 0;
    let cartDiscount = 0;
    const byRate: Record<string, { taxable: number; tax: number }> = {};
    const factor = 1 - cartDiscountPct / 100;
    for (const line of lines) {
      const qty = Number(line.quantity) || 0;
      const price = Number(line.unit_price) || 0;
      const lineDisc = Number(line.discount_amount) || 0;
      const gross = qty * price;
      const netBeforeCart = Math.max(0, gross - lineDisc);
      const net = netBeforeCart * factor;            // post-cart-discount taxable
      const rate = line.is_taxable ? (Number(line.tax_rate) || 0) : 0;
      const lineTax = (net * rate) / 100;
      subtotal += net;
      tax += lineTax;
      lineDiscount += lineDisc;
      cartDiscount += netBeforeCart - net;
      const key = `${rate}`;
      if (!byRate[key]) byRate[key] = { taxable: 0, tax: 0 };
      byRate[key].taxable += net;
      byRate[key].tax += lineTax;
    }
    return {
      subtotal,
      tax,
      lineDiscount,
      cartDiscount,
      discount: lineDiscount + cartDiscount,
      grand: subtotal + tax,
      byRate,
    };
  }, [lines, cartDiscountPct]);

  const totalTendered = useMemo(
    () => payments.reduce((acc, p) => acc + (Number(p.amount) || 0), 0),
    [payments],
  );

  // Lines that would drive stock negative at this location. Advisory only —
  // we surface them in a banner but never block the sale (the operator's count
  // may simply be stale). Empty when the tenant doesn't track stock here.
  const oversells = useMemo(() => {
    if (!tracksStock) return [];
    return lines
      .map((l) => {
        const onHand = onHandByProduct.get(l.product_id) ?? 0;
        const want = Number(l.quantity) || 0;
        return { name: l.product_name, want, onHand, short: want - onHand };
      })
      .filter((r) => r.short > 0);
  }, [lines, onHandByProduct, tracksStock]);

  // Auto-fill the single payment row to match the grand total whenever
  // the cart changes. Stops as soon as the user splits the tender or
  // explicitly types a non-matching amount.
  useEffect(() => {
    if (payments.length !== 1 || !paymentAutoFilled) return;
    const target = totals.grand.toFixed(2);
    if (payments[0].amount !== target) {
      setPayments((curr) => curr.map((p, i) => (i === 0 ? { ...p, amount: target } : p)));
    }
  }, [totals.grand, payments, paymentAutoFilled]);

  function addProduct(p: any) {
    // Coerce `p.tax_rate` from FK UUID to the numeric percentage the
    // backend invoice serializer expects. Without this, the POST to
    // /api/sales/invoices/manual/ rejects with
    //   "cart_lines.tax_rate: A valid number is required."
    // because DRF tries to parse the UUID as a Decimal.
    //
    // UX: clicking the same product twice in the picker should INCREMENT
    // the line's quantity rather than add a duplicate row. The picker
    // stays open after each click so the operator can rapid-tap several
    // products in a row. This matches POS-terminal cart behaviour and
    // halves the click count when invoicing multiple items.
    setLines((curr) => {
      const existingIdx = curr.findIndex((l) => l.product_id === p.id);
      if (existingIdx >= 0) {
        const existing = curr[existingIdx];
        const nextQty = (Number(existing.quantity) || 0) + 1;
        return curr.map((l, i) =>
          i === existingIdx ? { ...l, quantity: String(nextQty) } : l,
        );
      }
      return [...curr, {
        product_id: p.id,
        product_name: p.name,
        product_sku: p.sku,
        hs_code: p.hs_code ?? "",
        uom_code: p.uom ?? "PCS",
        quantity: "1",
        unit_price: priceInput(p.sale_price) || "0",
        tax_rate: resolveTaxRate(p.tax_rate),
        is_taxable: !!p.is_taxable,
        discount_amount: "0",
      }];
    });
    // Deliberately DO NOT close the picker or clear the search string
    // here — keeping both lets the operator add several items from the
    // same search filter in quick succession. The "Done" button + ESC
    // key both close the picker explicitly.
  }

  function updateLine(idx: number, patch: Partial<DraftLine>) {
    setLines((curr) => curr.map((line, i) => (i === idx ? { ...line, ...patch } : line)));
  }

  function removeLine(idx: number) {
    setLines((curr) => curr.filter((_, i) => i !== idx));
  }

  function setPaymentField(idx: number, patch: Partial<ManualInvoicePayment>) {
    setPayments((curr) => curr.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function addPayment() {
    // Split tender — user takes manual control of amounts.
    setPaymentAutoFilled(false);
    setPayments((curr) => [...curr, { payment_method: "cash", amount: "0" }]);
  }
  function removePayment(idx: number) {
    setPayments((curr) => {
      const next = curr.filter((_, i) => i !== idx);
      // Back down to one row → resume auto-fill.
      if (next.length === 1) setPaymentAutoFilled(true);
      return next;
    });
  }

  async function submit() {
    setError(null);
    // Only require explicit branch/terminal when the picker is visible.
    // Shape B office-invoice tenants don't have branches/terminals
    // modules; the server falls back to implicit defaults.
    if (showBranchPicker && !branchId) {
      setError("Pick a branch.");
      return;
    }
    if (showTerminalPicker && !terminalId) {
      setError("Pick a terminal.");
      return;
    }
    if (lines.length === 0) {
      setError("Add at least one line item.");
      return;
    }
    // Digital-Invoicing-only tenants raise the invoice with no payment, so skip
    // the tendered==grand check for them. POS/Both still require it to balance.
    if (!isDigitalOnly && Math.abs(totalTendered - totals.grand) > 0.01) {
      setError(`Payment Rs ${totalTendered.toFixed(2)} doesn't match grand total Rs ${totals.grand.toFixed(2)}.`);
      return;
    }
    try {
      // Defensive coerce again at submit time: even if `addProduct`
      // already resolved the UUID, the operator may have typed a blank
      // / non-numeric value into the per-line tax-rate input. Whatever
      // we send must parse as a Decimal on the server.
      const apiLines: ManualInvoiceLine[] = lines.map((l) => ({
        product: l.product_id,
        quantity: l.quantity,
        unit_price: l.unit_price,
        tax_rate: resolveTaxRate(l.tax_rate),
        is_taxable: l.is_taxable,
        discount_amount: l.discount_amount,
        hs_code: l.hs_code || undefined,
        uom_code: l.uom_code || undefined,
      }));
      const result = await create.mutateAsync({
        // Send branch/terminal only when chosen. Empty → server picks
        // implicit defaults for the office-invoice tenant.
        ...(branchId ? { branch: branchId } : {}),
        ...(terminalId ? { terminal: terminalId } : {}),
        // Deduct stock from the chosen warehouse (Digital Invoicing). Omitted
        // when the tenant has no warehouses → server stays branch-keyed.
        ...(warehouseId ? { warehouse: warehouseId } : {}),
        // Buyer is locked to the original on debit/credit notes; pass null
        // so the server copies the buyer block from reference_invoice.
        customer: debitContext ? null : (customerId || null),
        cart_lines: apiLines,
        // Cart-level discount as percent (0–100). Even when the operator
        // typed an Rs amount, we converted it to percent in the
        // `cartDiscountPct` memo so the wire format matches the server's
        // `cart_discount_pct` DecimalField(max_digits=5, dp=2). Omit
        // when zero so we don't pollute the audit log with no-op fields.
        ...(cartDiscountPct > 0
          ? { cart_discount_pct: cartDiscountPct.toFixed(2) }
          : {}),
        // DI-only tenants issue the invoice unpaid (no till payment); POS/Both
        // send the recorded payment rows.
        payments: isDigitalOnly
          ? []
          : payments.map((p) => ({ ...p, amount: String(p.amount) })),
        client_uuid: clientUuidRef.current,
        notes: notes || undefined,
        ...(debitContext
          ? {
              invoice_type: debitContext.invoiceType,
              reference_invoice: debitContext.referenceInvoiceId,
            }
          : {}),
      });
      // Take the user to the new invoice's detail page.
      navigate(`/sales/${result.id}`);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.data && typeof e.data === "object") {
        // DRF validation errors are { field: ["message", ...] } or
        // { field: [{ subfield: ["msg"] }] }. Render flat.
        const parts: string[] = [];
        const walk = (obj: any, prefix = ""): void => {
          if (Array.isArray(obj)) {
            obj.forEach((v) => walk(v, prefix));
          } else if (obj && typeof obj === "object") {
            for (const [k, v] of Object.entries(obj)) {
              walk(v, prefix ? `${prefix}.${k}` : k);
            }
          } else {
            parts.push(prefix ? `${prefix}: ${obj}` : String(obj));
          }
        };
        walk(e.data);
        setError(parts.join(" · ") || `API ${e.status}`);
      } else {
        setError(e instanceof Error ? e.message : "Save failed.");
      }
    }
  }

  const filteredProducts = products.data?.results ?? [];
  // Prefer the object captured when the buyer was picked (works even when the
  // searchable picker's current results don't include it); fall back to the
  // list for backwards compat.
  const selectedCustomer = customerId
    ? (selectedCustomerObj?.id === customerId
        ? selectedCustomerObj
        : customers.data?.results?.find((c) => c.id === customerId) ?? null)
    : null;
  const customerName = selectedCustomer?.name ?? "Walk-in";

  // Buyer block for the live preview. Walk-in flows pass null
  // everywhere so the preview shows "Unregistered / —". When a buyer
  // is picked we mirror the same Registered/Unregistered logic the
  // backend uses when computing buyerRegistrationType.
  const previewBuyer = {
    name: selectedCustomer?.name ?? null,
    ntn: selectedCustomer?.ntn ?? selectedCustomer?.cnic ?? null,
    province: selectedCustomer?.province ?? null,
    registrationType: (
      selectedCustomer?.registration_type === "registered"
        ? "Registered" : "Unregistered"
    ) as "Registered" | "Unregistered",
  };
  const previewLines = lines.map((l) => ({
    product_name: l.product_name,
    product_sku: l.product_sku,
    hs_code: l.hs_code || undefined,
    uom_code: l.uom_code || undefined,
    quantity: l.quantity,
    unit_price: l.unit_price,
    discount_pct: "0",            // line-level pct lives in cart_discount; per-line is fixed amount
    discount_amount: l.discount_amount,
    tax_rate: l.tax_rate,
    is_taxable: l.is_taxable,
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <Link to="/sales" className="text-sm text-muted-foreground hover:underline">
            ← Sales
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">
            {debitContext
              ? debitContext.invoiceType === "debit_note"
                ? "New debit note"
                : "New credit note"
              : "New invoice"}
          </h1>
          <p className="text-xs text-muted-foreground">
            {debitContext
              ? "Adds a separate FBR-validated invoice that references the original. Use this when items were missed or extra charges need to be billed."
              : "Manual entry — for wholesalers, service providers, or office staff issuing tax invoices outside the POS."}
          </p>
        </div>
      </div>

      {debitContext && (
        <Card className="border-amber-200 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/30">
          <CardContent className="flex items-center gap-3 py-3 text-sm">
            <FileText className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400" />
            <div className="flex-1">
              <span className="font-medium">Reference: </span>
              <Link
                to={`/sales/${debitContext.referenceInvoiceId}`}
                className="font-mono hover:underline"
              >
                {debitContext.referenceInvoiceNumber}
              </Link>
              {debitContext.buyerName && (
                <span className="ml-3 text-muted-foreground">
                  Buyer: {debitContext.buyerName}
                  {debitContext.buyerNtnCnic && ` (${debitContext.buyerNtnCnic})`}
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">
              Buyer block is locked — copied from the original at submit time.
            </span>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Header</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {/* Branch picker — only when the tenant has the branches
                module AND actually has >1 branch (single-branch tenants
                shouldn't have to pick the only option). */}
            {showBranchPicker && (branches.data?.results.length ?? 0) > 1 && (
              <div>
                <Label>Branch</Label>
                <Select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                  <option value="">—</option>
                  {branches.data?.results?.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </Select>
              </div>
            )}
            {/* Terminal picker — only when the tenant has the terminals
                module AND actually has >1 terminal under the chosen
                branch (or any branch). Hidden for office-invoice flow. */}
            {showTerminalPicker && (terminals.data?.results.length ?? 0) > 1 && (
              <div>
                <Label>Terminal / counter</Label>
                <Select value={terminalId} onChange={(e) => setTerminalId(e.target.value)}>
                  <option value="">—</option>
                  {terminals.data?.results
                    ?.filter((t) => !branchId || t.branch === branchId)
                    .map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                </Select>
              </div>
            )}
            {/* Warehouse picker — Digital Invoicing. Shows when the tenant has
                warehouses; the sale deducts stock from the chosen one. */}
            {showWarehousePicker && (
              <div>
                <Label>Deduct stock from</Label>
                <Select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
                  {branchWarehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}{w.is_default ? " (default)" : ""}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            {/* Buyer picker — only when the customers module is enabled
                (it's forced on, so this is always true today; keeping
                the conditional in case the forced flag ever changes). */}
            {showCustomerPicker && (
              <div>
                <Label>Buyer</Label>
                {/* Searchable picker — customers can be in the thousands, so we
                    search the server (/customers/?search=) rather than render
                    every option. Walk-in is always at the top of the list. */}
                <CustomerPicker
                  value={customerId}
                  selectedLabel={
                    selectedCustomer
                      ? `${selectedCustomer.name}${selectedCustomer.ntn ? ` · NTN ${selectedCustomer.ntn}` : selectedCustomer.cnic ? ` · CNIC ${selectedCustomer.cnic}` : ""}`
                      : null
                  }
                  onChange={(id, customer) => {
                    setCustomerId(id);
                    setSelectedCustomerObj(customer);
                  }}
                  disabled={!!debitContext}
                  walkInLabel={
                    debitContext
                      ? `From original: ${debitContext.buyerName ?? "Walk-in"}`
                      : "Walk-in (unregistered)"
                  }
                />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Live totals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span className="font-mono">{rs(totals.subtotal)}</span>
            </div>

            {/* Cart-level discount input.
                Two-mode toggle: % off OR Rs amount. The state for the
                actual percent applied lives in `cartDiscountPct` (memo
                above); both modes feed into it. We show the *effective*
                cart discount amount inline next to the input so the
                operator can see "10% = Rs 45" while typing. */}
            <div className="border-t pt-2 mt-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-muted-foreground text-xs">Invoice discount</span>
                {totals.cartDiscount > 0 && (
                  <span className="text-xs font-mono text-emerald-700">
                    −{rs(totals.cartDiscount)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*\.?[0-9]*"
                  value={cartDiscountInput}
                  onChange={(e) => setCartDiscountInput(e.target.value)}
                  className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-right text-sm font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Invoice discount value"
                />
                <button
                  type="button"
                  onClick={() => setCartDiscountMode("pct")}
                  aria-pressed={cartDiscountMode === "pct"}
                  className={`h-8 w-10 rounded-md border text-xs font-medium transition-colors ${
                    cartDiscountMode === "pct"
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background text-muted-foreground hover:bg-accent"
                  }`}
                >
                  %
                </button>
                <button
                  type="button"
                  onClick={() => setCartDiscountMode("rs")}
                  aria-pressed={cartDiscountMode === "rs"}
                  className={`h-8 w-10 rounded-md border text-xs font-medium transition-colors ${
                    cartDiscountMode === "rs"
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background text-muted-foreground hover:bg-accent"
                  }`}
                >
                  Rs
                </button>
              </div>
            </div>

            {totals.lineDiscount > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Line discounts</span>
                <span className="font-mono">−{rs(totals.lineDiscount)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tax</span>
              <span className="font-mono">{rs(totals.tax)}</span>
            </div>
            <div className="border-t pt-1.5 flex items-baseline justify-between text-base font-semibold">
              <span>Grand total</span>
              {/* Display-only: round the headline total to whole rupees
                  (450.08 → "Rs. 450"). The actual invoice/FBR amount is
                  unchanged — only this display is rounded. */}
              <span className="font-mono">Rs. {roundWhole(totals.grand)}</span>
            </div>
            {Object.entries(totals.byRate).filter(([rate]) => rate !== "0").length > 0 && (
              <div className="mt-2 border-t pt-2">
                <div className="text-xs text-muted-foreground">By rate band</div>
                {Object.entries(totals.byRate).map(([rate, v]) => (
                  <div key={rate} className="flex justify-between text-xs">
                    <span>{rate}%</span>
                    <span className="font-mono">{rs(v.taxable)} → tax {rs(v.tax)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm">Items</CardTitle>
          <Button
            variant="default"
            onClick={() => setShowProductPicker((v) => !v)}
          >
            <Plus className="mr-1 h-4 w-4" /> Add Products
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {showProductPicker && (
            <div className="border-b p-3 bg-muted/20">
              {/* Header strip: search + running count + Done button.
                  Layout: search input on the left grows, item-count
                  pill + Done button anchored on the right so the
                  operator always knows how many items they've added
                  in this picker session and can close in one click. */}
              <div className="flex items-center gap-2">
                <div className="relative w-full flex-1 sm:max-w-md">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-9"
                    placeholder="Search by SKU, barcode, name…"
                    value={productSearch}
                    autoFocus
                    onChange={(e) => setProductSearch(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        e.preventDefault();
                        setShowProductPicker(false);
                        setProductSearch("");
                      }
                      // Enter on a search with exactly one result =
                      // add that one product. Convenient for barcode-
                      // scanner workflows where the scanner appends
                      // a CR/LF after the SKU.
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (filteredProducts.length === 1) {
                          addProduct(filteredProducts[0]);
                        }
                      }
                    }}
                  />
                </div>
                {lines.length > 0 && (
                  <Badge variant="secondary" className="font-mono">
                    {lines.length} item{lines.length === 1 ? "" : "s"} added
                  </Badge>
                )}
                <Button
                  size="sm"
                  onClick={() => {
                    setShowProductPicker(false);
                    setProductSearch("");
                  }}
                >
                  Done
                </Button>
              </div>

              {/* Helper line so the operator knows the new behaviour
                  without needing docs. */}
              <p className="mt-1.5 text-xs text-muted-foreground">
                Click a product to add it. Click again to add another
                of the same item. Press <kbd className="rounded border border-muted-foreground/30 bg-background px-1 font-mono text-[10px]">Esc</kbd> or "Done" when finished.
              </p>

              <div className="mt-2 max-h-72 overflow-y-auto rounded-md border bg-background">
                {filteredProducts.length === 0 ? (
                  <p className="p-3 text-xs text-muted-foreground">
                    {productSearch ? "No matches." : "Start typing to find a product."}
                  </p>
                ) : (
                  <ul className="divide-y">
                    {filteredProducts.slice(0, 20).map((p: any) => {
                      // Show the operator at a glance which items they've
                      // already added, and how many. Encourages the click-
                      // again-to-bump-quantity pattern.
                      const inCart = lines.find((l) => l.product_id === p.id);
                      const addedQty = inCart ? Number(inCart.quantity) || 0 : 0;
                      const onHand = onHandByProduct.get(p.id);
                      return (
                        <li key={p.id}>
                          <button
                            type="button"
                            onClick={() => addProduct(p)}
                            className={`flex w-full items-center justify-between gap-3 p-2 text-left text-sm transition-colors ${
                              inCart
                                ? "bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:hover:bg-emerald-950/50"
                                : "hover:bg-muted"
                            }`}
                          >
                            <span className="min-w-0 flex-1 truncate">
                              <span className="font-mono text-xs text-muted-foreground">
                                {p.sku}
                              </span>{" "}
                              {p.name}
                            </span>
                            {tracksStock && onHand !== undefined && (
                              <span className={`shrink-0 text-xs ${onHand <= 0 ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}`}>
                                {onHand} in stock
                              </span>
                            )}
                            {inCart && (
                              <span className="shrink-0 rounded-full bg-emerald-600/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                                ✓ Added · qty {addedQty}
                              </span>
                            )}
                            <span className="shrink-0 font-mono text-muted-foreground">
                              {rs(p.sale_price)}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}

          {lines.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No products yet. Click "Add Products" to pick one.
            </p>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-xs">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">SKU / name</th>
                  <th className="px-3 py-2 text-left font-medium">HS code</th>
                  <th className="px-3 py-2 text-left font-medium">UoM</th>
                  {tracksStock && <th className="px-3 py-2 text-right font-medium">Avail.</th>}
                  <th className="px-3 py-2 text-right font-medium">Qty</th>
                  <th className="px-3 py-2 text-right font-medium">Rate (Rs)</th>
                  <th className="px-3 py-2 text-right font-medium">Tax %</th>
                  <th className="px-3 py-2 text-right font-medium">Discount</th>
                  <th className="px-3 py-2 text-right font-medium">Line total</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, idx) => {
                  const qty = Number(line.quantity) || 0;
                  const price = Number(line.unit_price) || 0;
                  const lineDiscount = Number(line.discount_amount) || 0;
                  const net = Math.max(0, qty * price - lineDiscount);
                  const rate = line.is_taxable ? (Number(line.tax_rate) || 0) : 0;
                  const lineTotal = net * (1 + rate / 100);
                  const onHand = onHandByProduct.get(line.product_id) ?? 0;
                  const over = tracksStock && qty > onHand;
                  return (
                    <tr key={idx} className="border-b">
                      <td className="px-3 py-2">
                        <div className="font-mono text-xs text-muted-foreground">{line.product_sku}</div>
                        <div>{line.product_name}</div>
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={line.hs_code}
                          onChange={(e) => updateLine(idx, { hs_code: e.target.value })}
                          className="h-8 w-24 text-xs"
                          placeholder="0101.2100"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Select
                          value={codeToOptionCode.get(line.uom_code) ?? line.uom_code}
                          onChange={(e) => updateLine(idx, { uom_code: e.target.value })}
                          className="h-8 w-40 text-xs"
                        >
                          {/* Keep the current value selectable even if not in
                              the deduped list (older data). */}
                          {!uomOptions.some((o) => o.code === (codeToOptionCode.get(line.uom_code) ?? line.uom_code)) && line.uom_code && (
                            <option value={line.uom_code}>{line.uom_code}</option>
                          )}
                          {uomOptions.map((o) => (
                            <option key={o.code} value={o.code}>{o.label}</option>
                          ))}
                        </Select>
                      </td>
                      {tracksStock && (
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          <span className={over ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}>
                            {onHand}
                          </span>
                        </td>
                      )}
                      <td className="px-3 py-2 text-right">
                        <NumberInput
                          mode="decimal"
                          value={line.quantity}
                          onChange={(v) => updateLine(idx, { quantity: v })}
                          className={`h-8 w-20 text-right text-xs ${over ? "border-amber-500" : ""}`}
                          aria-label="Quantity"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <NumberInput
                          mode="decimal"
                          value={line.unit_price}
                          onChange={(v) => updateLine(idx, { unit_price: v })}
                          className="h-8 w-24 text-right text-xs"
                          aria-label="Unit price"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <NumberInput
                          mode="decimal"
                          value={line.tax_rate}
                          onChange={(v) => updateLine(idx, { tax_rate: v })}
                          className="h-8 w-16 text-right text-xs"
                          disabled={!line.is_taxable}
                          aria-label="Tax rate"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <NumberInput
                          mode="decimal"
                          value={line.discount_amount}
                          onChange={(v) => updateLine(idx, { discount_amount: v })}
                          className="h-8 w-20 text-right text-xs"
                          aria-label="Discount amount"
                        />
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{rs(lineTotal)}</td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => removeLine(idx)}
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remove line"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Payments — POS/till concept. Hidden for Digital-Invoicing-only
            tenants, who raise the invoice unpaid (settled out-of-band). */}
        {!isDigitalOnly && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Payments</CardTitle>
            <Button size="sm" variant="outline" onClick={addPayment}>
              <Plus className="mr-1 h-4 w-4" /> Add payment
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {autoRateNote && (
              <div className="rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-xs text-blue-900 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100">
                {autoRateNote}
              </div>
            )}
            {payments.map((p, idx) => (
              <div key={idx} className="space-y-2 rounded-md border p-2">
                <div className="grid grid-cols-12 gap-2">
                  <Select
                    value={p.payment_method}
                    onChange={(e) => setPaymentField(idx, {
                      payment_method: e.target.value as ManualInvoicePayment["payment_method"],
                    })}
                    className="col-span-5"
                  >
                    {PAYMENT_METHODS.map((m) => (
                      <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                    ))}
                  </Select>
                  <NumberInput
                    mode="decimal"
                    value={p.amount}
                    onChange={(v) => {
                      setPaymentAutoFilled(false);
                      setPaymentField(idx, { amount: v });
                    }}
                    className="col-span-5 text-right font-mono"
                    placeholder="0.00"
                    aria-label="Payment amount"
                  />
                  <button
                    onClick={() => removePayment(idx)}
                    className="col-span-2 rounded-md text-muted-foreground hover:text-destructive"
                    aria-label="Remove payment"
                  >
                    <Trash2 className="mx-auto h-4 w-4" />
                  </button>
                </div>
                <PaymentExtraFields
                  payment={p}
                  onChange={(patch) => setPaymentField(idx, patch)}
                />
              </div>
            ))}
            {payments.length > 1 && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  // User wants to reset to one auto-filled row.
                  setPayments([{ payment_method: payments[0].payment_method, amount: totals.grand.toFixed(2) }]);
                  setPaymentAutoFilled(true);
                }}
              >
                Collapse to single payment
              </Button>
            )}
            <div className="flex justify-between border-t pt-2 text-sm">
              <span className="text-muted-foreground">Tendered</span>
              <span className={`font-mono ${
                Math.abs(totalTendered - totals.grand) < 0.01
                  ? "text-green-700" : "text-amber-700"
              }`}>
                {rs(totalTendered)}
              </span>
            </div>
          </CardContent>
        </Card>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes for this invoice (visible in admin only)…"
              className="w-full rounded-md border bg-background px-2 py-1 text-sm"
            />
            <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              <span>Buyer:</span>
              <Badge variant="outline">{customerName}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Saved as a draft locally. On the next screen you can
              "Validate with FBR" (free dry-run) and then "Submit to FBR"
              when ready — that's when PRAL issues the FBR Invoice Number.
            </p>
          </CardContent>
        </Card>
      </div>

      {oversells.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50/70 p-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Selling more than you have on hand</p>
            <ul className="mt-1 list-inside list-disc text-xs">
              {oversells.map((o) => (
                <li key={o.name}>
                  {o.name}: on hand {o.onHand}, invoicing {o.want} (short {o.short})
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs">
              You can still create this invoice — stock will go negative. Check the count or restock if this looks wrong.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Live A4-ish preview so the operator can sanity-check the
          buyer + totals before committing. The server still generates
          the canonical PDF (with FBR seal + QR) after save. */}
      <InvoicePreview
        buyer={previewBuyer}
        lines={previewLines}
        // Per-line discounts are already folded into previewLines.
        // The cart-level percent is layered on top by InvoicePreview's
        // own math. We pass our derived cartDiscountPct verbatim (it's
        // already capped to 100 and converted from Rs → pct when the
        // operator typed an Rs amount).
        cartDiscountPct={cartDiscountPct.toFixed(2)}
        invoiceType={debitContext?.invoiceType ?? "sale"}
      />

      {/* Action footer.
          Manual invoices are NOT auto-submitted to FBR — the operator
          clicks "Create invoice" to save locally, then runs "Validate
          with FBR" + "Submit to FBR" from the invoice detail page when
          they're confident the data is correct. Splitting saves +
          submission lets the operator review the saved invoice (line
          totals, buyer, tax breakdown) before committing to PRAL,
          which is irrevocable once an FBR Invoice Number is issued. */}
      <div className="flex flex-col items-end gap-2">
        <p className="text-xs text-muted-foreground">
          The invoice will be saved locally as a draft. You can validate
          + submit it to FBR from the invoice detail page.
        </p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/sales")}>Cancel</Button>
          <Button onClick={submit} loading={create.isPending}>
            {create.isPending ? "Saving…" : "Create invoice"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Per-method extra fields for payments. Mirrors what each adapter
 * validates server-side (apps/payments/adapters/<method>.py):
 *
 *   card_credit / card_debit  → card_last4 (4 digits) + card_auth_code
 *                               (6 digits); RRN optional
 *   easypaisa / jazzcash       → wallet_transaction_id
 *   raast                      → raast_transaction_id
 *   cheque                     → cheque_number, bank_name, cheque_date
 *   bank_transfer              → bank_name, bank_reference
 *
 * cash and store_credit need no extra fields.
 */
function PaymentExtraFields({
  payment, onChange,
}: {
  payment: ManualInvoicePayment;
  onChange: (patch: Partial<ManualInvoicePayment>) => void;
}) {
  const m = payment.payment_method;
  if (m === "cash" || m === "store_credit") return null;

  if (m === "card_credit" || m === "card_debit") {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <NumberInput
          mode="integer"
          maxLength={4}
          value={payment.card_last4 ?? ""}
          onChange={(v) => onChange({ card_last4: v })}
          placeholder="Last 4 digits"
          aria-label="Card last 4 digits"
          className="text-xs"
        />
        <NumberInput
          mode="integer"
          maxLength={6}
          value={payment.card_auth_code ?? ""}
          onChange={(v) => onChange({ card_auth_code: v })}
          placeholder="Auth code (6 digits)"
          aria-label="Card auth code"
          className="text-xs"
        />
        <Input
          value={payment.card_rrn ?? ""}
          onChange={(e) => onChange({ card_rrn: e.target.value })}
          placeholder="RRN (optional)"
          className="text-xs"
        />
      </div>
    );
  }

  if (m === "easypaisa" || m === "jazzcash") {
    return (
      <Input
        value={payment.wallet_transaction_id ?? ""}
        onChange={(e) => onChange({ wallet_transaction_id: e.target.value })}
        placeholder="Wallet transaction ID — from the customer's app"
        className="text-xs"
      />
    );
  }

  if (m === "raast") {
    return (
      <Input
        value={payment.raast_transaction_id ?? ""}
        onChange={(e) => onChange({ raast_transaction_id: e.target.value })}
        placeholder="Raast transaction ID — from the customer's banking app"
        className="text-xs"
      />
    );
  }

  if (m === "cheque") {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Input
          value={payment.cheque_number ?? ""}
          onChange={(e) => onChange({ cheque_number: e.target.value })}
          placeholder="Cheque number"
          className="text-xs"
        />
        <Input
          value={payment.bank_name ?? ""}
          onChange={(e) => onChange({ bank_name: e.target.value })}
          placeholder="Bank name"
          className="text-xs"
        />
        <Input
          type="date"
          value={payment.cheque_date ?? ""}
          onChange={(e) => onChange({ cheque_date: e.target.value })}
          className="text-xs"
        />
      </div>
    );
  }

  if (m === "bank_transfer") {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Input
          value={payment.bank_name ?? ""}
          onChange={(e) => onChange({ bank_name: e.target.value })}
          placeholder="Bank name"
          className="text-xs"
        />
        <Input
          value={payment.bank_reference ?? ""}
          onChange={(e) => onChange({ bank_reference: e.target.value })}
          placeholder="Bank reference"
          className="text-xs"
        />
      </div>
    );
  }

  return null;
}
