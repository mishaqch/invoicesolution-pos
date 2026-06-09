import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HsCodePicker } from "@/components/ui/hs-code-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { Select } from "@/components/ui/select";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useCategories,
  useCreateBatch,
  useCreateProduct,
  usePostAdjustment,
  useProduct,
  useProductBatches,
  useStockLevels,
  useTaxRates,
  useTenantSetup,
  useUoms,
  useUpdateProduct,
} from "@/lib/queries";
import { useIsModuleEnabled, useIsPharmacy, useIsRestaurant } from "@/features/modules/hooks";
import {
  useModifierGroups,
  useProductModifierGroups,
  useSaveProductModifierGroups,
} from "@/lib/queries";
import type { ProductBatch, StockLevel } from "@pos/shared/types";
import { money } from "@/lib/utils";

interface FormValues {
  name: string;
  name_ur: string;
  sku: string;
  barcode: string;
  category: string;
  uom: string;
  tax_rate: string;
  is_taxable: boolean;
  cost_price: string;
  sale_price: string;
  retail_price: string;
  min_sale_price: string;
  reorder_level: string;
  is_active: boolean;
  description: string;
  // PRAL HS code — required for FBR Digital Invoicing. Every invoice
  // line item PRAL receives must carry an hsCode; the cart line copies
  // this value off the product at sale time. Free-text wasn't a viable
  // UX so we use an autocomplete against the live ~7,900-code catalog.
  hs_code: string;
  // Pakistan 3rd-Schedule flag. When on, FBR submission uses retail_price
  // as the taxable base (saleType="3rd Schedule Goods") instead of
  // sale_price. Required by PRAL for sugar / drinks / biscuits /
  // cigarettes / mobile phones / tea etc. retail_price must be set
  // when this is on (backend serializer enforces this).
  is_third_schedule: boolean;
  // Pharmacy / date-sensitive goods: when on, stock is tracked per batch
  // (batch number + expiry). Surfaced only for pharmacy tenants. Enables the
  // Batches card on edit and FEFO batch selection at the terminal.
  is_batch_tracked: boolean;
}

const blank: FormValues = {
  name: "", name_ur: "", sku: "", barcode: "",
  category: "", uom: "PCS", tax_rate: "",
  is_taxable: true,
  cost_price: "0", sale_price: "0", retail_price: "",
  min_sale_price: "", reorder_level: "",
  is_active: true, description: "",
  hs_code: "",
  is_third_schedule: false,
  is_batch_tracked: false,
};

export default function ProductEdit() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === "new";
  const navigate = useNavigate();

  const { data: existing } = useProduct(isNew ? undefined : id);
  const uoms = useUoms();
  const taxRates = useTaxRates();
  const categories = useCategories();
  const { data: setup } = useTenantSetup();
  const di = setup?.business_mode === "digital_invoicing";
  const noun = di ? "item" : "product";

  // Opening stock (NEW product only): an optional starting quantity recorded as
  // an opening_balance stock movement so the product is immediately stocked —
  // without breaking the audit ledger (stock = sum of movements, not a field).
  // Only relevant to tenants that track inventory (POS, not digital-invoicing).
  const inventoryOn = useIsModuleEnabled("inventory");
  // Pharmacy tenants get the batch/expiry tools (the is_batch_tracked toggle +
  // the Batches card on edit). Grocery tenants never see them.
  const isPharmacy = useIsPharmacy();
  // Restaurant tenants get the Modifiers card (attach Size/Add-ons groups).
  const isRestaurant = useIsRestaurant();
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];
  const postAdjustment = usePostAdjustment();
  const [openingStock, setOpeningStock] = useState("");
  const [openingBranch, setOpeningBranch] = useState("");
  const showOpeningStock = isNew && inventoryOn && !di;
  // On EDIT (existing product), show live per-branch stock + an Adjust control.
  const showStockOnEdit = !isNew && inventoryOn && !di;
  const { data: stockData } = useStockLevels(
    showStockOnEdit && id ? { product: id } : {},
  );

  const create = useCreateProduct();
  const update = useUpdateProduct();
  const saving = create.isPending || update.isPending;

  const [values, setValues] = useState<FormValues>(blank);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existing) {
      setValues({
        name: existing.name,
        name_ur: existing.name_ur,
        sku: existing.sku,
        barcode: existing.barcode ?? "",
        category: existing.category ?? "",
        uom: existing.uom,
        tax_rate: existing.tax_rate ?? "",
        is_taxable: existing.is_taxable,
        cost_price: existing.cost_price ?? "0",
        sale_price: existing.sale_price,
        retail_price: existing.retail_price ?? "",
        min_sale_price: existing.min_sale_price ?? "",
        reorder_level: existing.reorder_level ?? "",
        is_active: existing.is_active,
        description: existing.description,
        hs_code: existing.hs_code ?? "",
        is_third_schedule: existing.is_third_schedule ?? false,
        is_batch_tracked: existing.is_batch_tracked ?? false,
      });
    }
  }, [existing]);

  function set<K extends keyof FormValues>(key: K, v: FormValues[K]) {
    setValues((s) => ({ ...s, [key]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Client-side guard: HS code is required for FBR submission.
    // The backend serializer also validates this — defence in depth.
    if (!values.hs_code) {
      setError(
        "HS code is required. Every product line submitted to FBR must "
        + "carry a valid HS code from PRAL's catalog. Pick one from the "
        + "field above.",
      );
      return;
    }
    // 3rd-Schedule items must have a retail_price set (the value PRAL
    // uses as the taxable base). Catch it client-side so the operator
    // sees the requirement near the field they need to fix, rather
    // than after a roundtrip.
    if (values.is_third_schedule) {
      const retail = Number(values.retail_price);
      if (!values.retail_price || Number.isNaN(retail) || retail <= 0) {
        setError(
          "Retail price is required and must be > 0 when '3rd Schedule "
          + "item' is on. PRAL charges tax on retail price for 3rd-"
          + "Schedule goods (sugar, biscuits, drinks, cigarettes, mobile "
          + "phones, tea). Set the Retail price above before saving.",
        );
        return;
      }
    }
    const payload = {
      ...values,
      barcode: values.barcode || null,
      category: values.category || null,
      tax_rate: values.tax_rate || null,
      retail_price: values.retail_price || null,
      min_sale_price: values.min_sale_price || null,
      reorder_level: values.reorder_level || null,
    };
    try {
      if (isNew) {
        const created = await create.mutateAsync(payload);
        // Record opening stock as an opening_balance movement (keeps the
        // ledger correct). Best-effort: a failure here shouldn't lose the
        // product the user just created — surface it but keep going.
        const qty = Number(openingStock);
        const branch = openingBranch || branches[0]?.id;
        if (showOpeningStock && qty > 0 && branch && created?.id) {
          try {
            await postAdjustment.mutateAsync({
              branch,
              product: created.id,
              quantity: String(qty),
              movement_type: "opening_balance",
              reason: "Opening stock (set at product creation)",
            });
          } catch (stockErr) {
            window.alert(
              "Product created, but opening stock could not be recorded: "
              + extractApiErrorMessage(stockErr)
              + "\nYou can set it later via Inventory → Adjustments.",
            );
          }
        }
      } else {
        await update.mutateAsync({ id: id!, ...payload });
      }
      navigate("/catalog/products");
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/catalog/products" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to {noun}s
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">
        {isNew ? `New ${noun}` : values.name || `Edit ${noun}`}
      </h1>

      <form onSubmit={onSubmit} className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Basic</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Name *" id="name">
              <Input id="name" value={values.name} onChange={(e) => set("name", e.target.value)} required />
            </Field>
            <Field label="Name (Urdu)" id="name_ur">
              <Input id="name_ur" value={values.name_ur} onChange={(e) => set("name_ur", e.target.value)} dir="rtl" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="SKU *" id="sku">
                <Input id="sku" value={values.sku} onChange={(e) => set("sku", e.target.value)} required />
              </Field>
              <Field label="Barcode" id="barcode">
                <Input id="barcode" value={values.barcode} onChange={(e) => set("barcode", e.target.value)} />
              </Field>
            </div>
            <Field label="Category" id="category">
              <Select id="category" value={values.category} onChange={(e) => set("category", e.target.value)}>
                <option value="">— None —</option>
                {categories.data?.results.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pricing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Cost price" id="cost_price">
                <NumberInput id="cost_price" mode="decimal" value={values.cost_price} onChange={(v) => set("cost_price", v)} />
              </Field>
              <Field label="Sale price *" id="sale_price">
                <NumberInput id="sale_price" mode="decimal" value={values.sale_price} onChange={(v) => set("sale_price", v)} required />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Retail price" id="retail_price">
                <NumberInput id="retail_price" mode="decimal" value={values.retail_price} onChange={(v) => set("retail_price", v)} />
              </Field>
              <Field label="Min sale price" id="min_sale_price">
                <NumberInput id="min_sale_price" mode="decimal" value={values.min_sale_price} onChange={(v) => set("min_sale_price", v)} />
              </Field>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tax & FBR</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="HS code *" id="hs_code">
              <HsCodePicker
                id="hs_code"
                value={values.hs_code}
                onChange={(code) => set("hs_code", code)}
                required
              />
              <p className="mt-1 text-xs text-muted-foreground">
                The PRAL HS code that appears on every invoice line for
                this product. Required for FBR submission. Type to
                search ~7,900 codes by code or description.
              </p>
            </Field>
            <Field label="Unit of measure *" id="uom">
              <Select id="uom" value={values.uom} onChange={(e) => set("uom", e.target.value)} required>
                {uoms.data?.map((u) => (
                  <option key={u.code} value={u.code}>{u.code} — {u.name_en}</option>
                ))}
              </Select>
            </Field>
            <Field label="Tax rate" id="tax_rate">
              <Select id="tax_rate" value={values.tax_rate} onChange={(e) => set("tax_rate", e.target.value)}>
                <option value="">— None —</option>
                {taxRates.data?.results.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={values.is_taxable}
                onChange={(e) => set("is_taxable", e.target.checked)}
              />
              Taxable
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={values.is_third_schedule}
                onChange={(e) => set("is_third_schedule", e.target.checked)}
              />
              <span>
                <span className="font-medium">3rd Schedule item</span>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Tick for goods taxed on retail price (MRP) rather than
                  sale price — sugar, biscuits, carbonated drinks,
                  cigarettes, mobile phones, tea, infant milk. Requires
                  Retail price to be set above. Without this, PRAL
                  rejects the invoice line with error 0122.
                </p>
              </span>
            </label>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Inventory</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {showOpeningStock && (
              <div className="rounded-md border border-info-soft bg-info-soft/30 p-3 space-y-3">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Opening stock</span> —
                  how many you have in hand right now. Recorded as the starting
                  balance; later changes go through Inventory → Adjustments so the
                  stock history stays accurate.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Opening stock qty" id="opening_stock">
                    <NumberInput
                      id="opening_stock" mode="decimal"
                      value={openingStock} onChange={setOpeningStock}
                    />
                  </Field>
                  {branches.length > 1 && (
                    <Field label="Branch" id="opening_branch">
                      <Select
                        id="opening_branch"
                        value={openingBranch || branches[0]?.id || ""}
                        onChange={(e) => setOpeningBranch(e.target.value)}
                      >
                        {branches.map((b) => (
                          <option key={b.id} value={b.id}>{b.name}</option>
                        ))}
                      </Select>
                    </Field>
                  )}
                </div>
              </div>
            )}
            {showStockOnEdit && id && (
              <StockOnEdit
                productId={id}
                stock={stockData?.results ?? []}
                branches={branches}
              />
            )}
            <Field label="Reorder level" id="reorder_level">
              <NumberInput id="reorder_level" mode="decimal" value={values.reorder_level} onChange={(v) => set("reorder_level", v)} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={values.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
              />
              Active
            </label>
            {isPharmacy && inventoryOn && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={values.is_batch_tracked}
                  onChange={(e) => set("is_batch_tracked", e.target.checked)}
                />
                Batch-tracked (track stock per batch &amp; expiry)
              </label>
            )}
          </CardContent>
        </Card>

        {isPharmacy && inventoryOn && !isNew && id && values.is_batch_tracked && (
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Batches</CardTitle>
            </CardHeader>
            <CardContent>
              <BatchManager productId={id} branches={branches} />
            </CardContent>
          </Card>
        )}

        {isRestaurant && !isNew && id && (
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Modifiers</CardTitle>
            </CardHeader>
            <CardContent>
              <ModifierAttach productId={id} />
            </CardContent>
          </Card>
        )}

        <div className="md:col-span-2 flex items-center justify-between">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="ml-auto flex gap-2">
            <Link to="/catalog/products">
              <Button type="button" variant="outline">Cancel</Button>
            </Link>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : isNew ? "Create" : "Save"}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

/**
 * On the Edit page: show this product's live stock per branch (read-only) and
 * an "Adjust stock" control. Adjusting records a proper stock MOVEMENT (with a
 * reason) — never overwrites a number — so the audit ledger stays intact.
 * Supports either setting an absolute count (we compute the +/- delta) or
 * entering a delta directly.
 */
function StockOnEdit({
  productId,
  stock,
  branches,
}: {
  productId: string;
  stock: StockLevel[];
  branches: { id: string; name: string }[];
}) {
  const postAdjustment = usePostAdjustment();
  const [branch, setBranch] = useState(branches[0]?.id ?? "");
  const [mode, setMode] = useState<"set" | "delta">("set");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const branchName = (bid: string) => branches.find((b) => b.id === bid)?.name ?? bid;
  const stockFor = (bid: string) =>
    stock.find((s) => s.branch === bid && s.variant === null)?.quantity ?? "0";
  const effectiveBranch = branch || branches[0]?.id || "";

  async function apply() {
    setMsg(null);
    const num = Number(value);
    if (!effectiveBranch) { setMsg({ ok: false, text: "Pick a branch." }); return; }
    if (Number.isNaN(num)) { setMsg({ ok: false, text: "Enter a number." }); return; }
    if (!reason.trim()) { setMsg({ ok: false, text: "A reason is required (for the audit log)." }); return; }

    // Compute signed delta. "set" → new_total - current; "delta" → as typed.
    const current = Number(stockFor(effectiveBranch));
    const delta = mode === "set" ? num - current : num;
    if (delta === 0) { setMsg({ ok: false, text: "No change." }); return; }
    const movement_type = delta > 0 ? "adjustment_in" : "adjustment_out";

    try {
      await postAdjustment.mutateAsync({
        branch: effectiveBranch,
        product: productId,
        quantity: String(Math.abs(delta)),
        movement_type,
        reason: reason.trim(),
      });
      setMsg({ ok: true, text: `Stock ${delta > 0 ? "increased" : "reduced"} by ${Math.abs(delta)}.` });
      setValue(""); setReason("");
    } catch (err) {
      setMsg({ ok: false, text: extractApiErrorMessage(err) });
    }
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-3">
      <div className="text-sm font-medium">Current stock</div>
      <div className="space-y-1">
        {stock.length === 0 ? (
          <p className="text-xs text-muted-foreground">No stock recorded yet.</p>
        ) : (
          stock
            .filter((s) => s.variant === null)
            .map((s) => (
              <div key={s.id} className="flex justify-between text-sm">
                <span className="text-muted-foreground">{branchName(s.branch)}</span>
                <span className="font-mono">{s.quantity}</span>
              </div>
            ))
        )}
      </div>

      <div className="border-t pt-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">Adjust stock</div>
        <div className="grid grid-cols-2 gap-2">
          {branches.length > 1 && (
            <Select value={effectiveBranch} onChange={(e) => setBranch(e.target.value)}>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
          )}
          <Select value={mode} onChange={(e) => setMode(e.target.value as "set" | "delta")}>
            <option value="set">Set new count</option>
            <option value="delta">Add / subtract (+/-)</option>
          </Select>
          <NumberInput
            mode="decimal" value={value} onChange={setValue}
            aria-label="Stock value"
          />
          <Input
            placeholder="Reason (e.g. recount, damage)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="outline"
            loading={postAdjustment.isPending} onClick={apply}>
            Apply adjustment
          </Button>
          {msg && (
            <span className={`text-xs ${msg.ok ? "text-success-soft-foreground" : "text-destructive"}`}>
              {msg.text}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Pharmacy batch management for one product: lists existing batches (soonest
 * expiry first, with an expired/near-expiry highlight) and an add-batch form.
 * Adding a batch creates the batch AND records an opening-stock movement
 * server-side, so the aggregate stock + audit ledger stay consistent.
 */
function BatchManager({
  productId,
  branches,
}: {
  productId: string;
  branches: { id: string; name: string }[];
}) {
  const { data, isLoading } = useProductBatches(productId);
  const createBatch = useCreateBatch();
  const [batchNumber, setBatchNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [mfg, setMfg] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [branch, setBranch] = useState(branches[0]?.id ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const batches = data?.results ?? [];
  const effectiveBranch = branch || branches[0]?.id || "";

  // Expiry status for a batch row (drives colour + label).
  function expiryStatus(b: ProductBatch): { label: string; cls: string } | null {
    if (!b.expiry_date) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const exp = new Date(b.expiry_date + "T00:00:00");
    const days = Math.round((exp.getTime() - today.getTime()) / 86_400_000);
    if (days < 0) return { label: "Expired", cls: "text-destructive font-medium" };
    if (days <= 30) return { label: `${days}d left`, cls: "text-warning-soft-foreground font-medium" };
    if (days <= 90) return { label: `${days}d left`, cls: "text-muted-foreground" };
    return null;
  }

  async function add() {
    setMsg(null);
    if (!batchNumber.trim()) { setMsg({ ok: false, text: "Batch number is required." }); return; }
    const n = Number(qty);
    if (Number.isNaN(n) || n <= 0) { setMsg({ ok: false, text: "Enter a quantity > 0." }); return; }
    if (!effectiveBranch) { setMsg({ ok: false, text: "Pick a branch." }); return; }
    try {
      await createBatch.mutateAsync({
        product: productId,
        batch_number: batchNumber.trim(),
        expiry_date: expiry || null,
        manufactured_date: mfg || null,
        cost_price: cost || null,
        initial_quantity: String(n),
        branch: effectiveBranch,
      });
      setMsg({ ok: true, text: `Batch ${batchNumber.trim()} added.` });
      setBatchNumber(""); setExpiry(""); setMfg(""); setQty(""); setCost("");
    } catch (err) {
      setMsg({ ok: false, text: extractApiErrorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      {/* Existing batches */}
      <div className="rounded-md border">
        <div className="grid grid-cols-[1.2fr_1fr_0.8fr_1fr_0.8fr] gap-2 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
          <span>Batch #</span><span>Expiry</span><span>On hand</span><span>Branch</span><span>Cost</span>
        </div>
        {isLoading ? (
          <p className="px-3 py-3 text-sm text-muted-foreground">Loading batches…</p>
        ) : batches.length === 0 ? (
          <p className="px-3 py-3 text-sm text-muted-foreground">No batches yet. Add one below.</p>
        ) : (
          batches.map((b) => {
            const st = expiryStatus(b);
            return (
              <div key={b.id} className="grid grid-cols-[1.2fr_1fr_0.8fr_1fr_0.8fr] gap-2 border-b px-3 py-2 text-sm last:border-0">
                <span className="font-medium">{b.batch_number}</span>
                <span className={st?.cls ?? "text-muted-foreground"}>
                  {b.expiry_date ?? "—"}{st ? ` · ${st.label}` : ""}
                </span>
                <span className="font-mono">{b.current_quantity}</span>
                <span className="text-muted-foreground">{b.branch_name ?? "—"}</span>
                <span className="font-mono">{b.cost_price ? money(b.cost_price) : "—"}</span>
              </div>
            );
          })
        )}
      </div>

      {/* Add batch */}
      <div className="rounded-md border bg-muted/30 p-3 space-y-3">
        <div className="text-xs font-medium text-muted-foreground">Add batch</div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Field label="Batch number" id="batch_number">
            <Input id="batch_number" value={batchNumber} onChange={(e) => setBatchNumber(e.target.value)} />
          </Field>
          <Field label="Expiry date" id="batch_expiry">
            <Input id="batch_expiry" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </Field>
          <Field label="Manufactured (optional)" id="batch_mfg">
            <Input id="batch_mfg" type="date" value={mfg} onChange={(e) => setMfg(e.target.value)} />
          </Field>
          <Field label="Quantity" id="batch_qty">
            <NumberInput id="batch_qty" mode="decimal" value={qty} onChange={setQty} />
          </Field>
          <Field label="Cost price (optional)" id="batch_cost">
            <NumberInput id="batch_cost" mode="decimal" value={cost} onChange={setCost} />
          </Field>
          {branches.length > 1 && (
            <Field label="Branch" id="batch_branch">
              <Select id="batch_branch" value={effectiveBranch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </Select>
            </Field>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" loading={createBatch.isPending} onClick={add}>
            Add batch
          </Button>
          {msg && (
            <span className={`text-xs ${msg.ok ? "text-success-soft-foreground" : "text-destructive"}`}>
              {msg.text}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Restaurant: attach modifier groups (Size, Add-ons) to this menu item.
 * The terminal then shows ONLY these groups when the item is added. Checkboxes
 * against the tenant's group catalog; PUT replaces the product's links.
 */
function ModifierAttach({ productId }: { productId: string }) {
  const { data: catalog } = useModifierGroups();
  const { data: current } = useProductModifierGroups(productId);
  const save = useSaveProductModifierGroups();
  const groups = catalog?.results ?? [];
  const [selected, setSelected] = useState<string[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Initialise from the server once both queries land.
  const attached = selected ?? current?.group_ids ?? [];

  function toggle(id: string) {
    const base = selected ?? current?.group_ids ?? [];
    setSelected(base.includes(id) ? base.filter((g) => g !== id) : [...base, id]);
  }

  async function persist() {
    setMsg(null);
    try {
      await save.mutateAsync({ productId, groupIds: attached });
      setMsg("Saved.");
      setSelected(null);
    } catch (err) {
      setMsg(extractApiErrorMessage(err));
    }
  }

  if (groups.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No modifier groups yet. Create them under Restaurant → Modifiers, then attach here.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Tick the option groups this item offers (e.g. Size, Add-ons). The terminal shows only the attached groups.
      </p>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {groups.map((g) => (
          <label key={g.id} className="flex items-center gap-2 rounded-md border p-2 text-sm">
            <input
              type="checkbox"
              checked={attached.includes(g.id)}
              onChange={() => toggle(g.id)}
            />
            <span>
              {g.name}
              <span className="ml-1 text-xs text-muted-foreground">
                ({g.min_select > 0 ? "required" : "optional"})
              </span>
            </span>
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" loading={save.isPending} onClick={persist}>Save modifiers</Button>
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </div>
    </div>
  );
}
