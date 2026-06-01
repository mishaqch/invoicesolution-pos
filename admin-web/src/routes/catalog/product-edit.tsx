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
  useCategories,
  useCreateProduct,
  useProduct,
  useTaxRates,
  useTenantSetup,
  useUoms,
  useUpdateProduct,
} from "@/lib/queries";

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
        await create.mutateAsync(payload);
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
          </CardContent>
        </Card>

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
