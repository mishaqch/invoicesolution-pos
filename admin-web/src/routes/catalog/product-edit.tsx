import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  useCategories,
  useCreateProduct,
  useProduct,
  useTaxRates,
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
}

const blank: FormValues = {
  name: "", name_ur: "", sku: "", barcode: "",
  category: "", uom: "PCS", tax_rate: "",
  is_taxable: true,
  cost_price: "0", sale_price: "0", retail_price: "",
  min_sale_price: "", reorder_level: "",
  is_active: true, description: "",
};

export default function ProductEdit() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === "new";
  const navigate = useNavigate();

  const { data: existing } = useProduct(isNew ? undefined : id);
  const uoms = useUoms();
  const taxRates = useTaxRates();
  const categories = useCategories();

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
      });
    }
  }, [existing]);

  function set<K extends keyof FormValues>(key: K, v: FormValues[K]) {
    setValues((s) => ({ ...s, [key]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
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
      const message = err instanceof Error ? err.message : "Save failed.";
      setError(message);
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/catalog/products" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to products
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">
        {isNew ? "New product" : values.name || "Edit product"}
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
                <Input id="cost_price" inputMode="decimal" value={values.cost_price} onChange={(e) => set("cost_price", e.target.value)} />
              </Field>
              <Field label="Sale price *" id="sale_price">
                <Input id="sale_price" inputMode="decimal" value={values.sale_price} onChange={(e) => set("sale_price", e.target.value)} required />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Retail price" id="retail_price">
                <Input id="retail_price" inputMode="decimal" value={values.retail_price} onChange={(e) => set("retail_price", e.target.value)} />
              </Field>
              <Field label="Min sale price" id="min_sale_price">
                <Input id="min_sale_price" inputMode="decimal" value={values.min_sale_price} onChange={(e) => set("min_sale_price", e.target.value)} />
              </Field>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tax</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
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
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Inventory</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Reorder level" id="reorder_level">
              <Input id="reorder_level" inputMode="decimal" value={values.reorder_level} onChange={(e) => set("reorder_level", e.target.value)} />
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
