/**
 * FbrDetailsPanel — the inline "FBR cockpit" for one stock row.
 *
 * The owner manages a product's whole fiscal identity (Description, HS code,
 * UoM, Sale type, SRO schedule + item serial, Tax rate, Retail price) right
 * from the Stock screen, without bouncing to the Product page.
 *
 * IMPORTANT — single source of truth: these fields LIVE ON THE PRODUCT. This
 * panel reads the current values off the stock row (the API embeds them) and
 * SAVES by PATCHing /catalog/products/{id}/ — it does NOT store a second copy
 * on the stock/warehouse row. That keeps one product = one fiscal identity, so
 * the same SKU can never carry two different HS codes / sale types across
 * warehouses (which PRAL would reject). The same server-side validation that
 * guards the Product form (HS required, sale-type valid, 3rd-Schedule needs a
 * retail price) therefore applies here unchanged.
 */
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { HsCodePicker } from "@/components/ui/hs-code-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { Select } from "@/components/ui/select";
import { extractApiErrorMessage } from "@/lib/api";
import { useSaleTypes, useTaxRates, useUoms, useUpdateProduct } from "@/lib/queries";
import type { StockLevel } from "@pos/shared/types";

interface FbrForm {
  description: string;
  hs_code: string;
  uom: string;
  sale_type: string;
  sro_schedule_no: string;
  sro_item_serial_no: string;
  tax_rate: string;
  retail_price: string;
}

export function FbrDetailsPanel({
  stock,
  onSaved,
}: {
  stock: StockLevel;
  onSaved?: () => void;
}) {
  const uoms = useUoms();
  const saleTypes = useSaleTypes();
  const taxRates = useTaxRates();
  const update = useUpdateProduct();
  const toast = useToast();

  // Seed the form from the embedded stock-row FBR fields (which mirror the
  // product). Re-seed if the row changes (e.g. after a save invalidates it).
  const seed = useMemo<FbrForm>(
    () => ({
      description: stock.product_description ?? "",
      hs_code: stock.hs_code ?? "",
      uom: stock.uom ?? "",
      sale_type: stock.sale_type ?? "Goods at standard rate (default)",
      sro_schedule_no: stock.sro_schedule_no ?? "",
      sro_item_serial_no: stock.sro_item_serial_no ?? "",
      tax_rate: stock.tax_rate ?? "",
      retail_price: stock.retail_price ?? "",
    }),
    [stock],
  );
  const [form, setForm] = useState<FbrForm>(seed);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setForm(seed), [seed]);

  function set<K extends keyof FbrForm>(k: K, v: FbrForm[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  // 3rd-Schedule (retail-price taxation) is derived from the sale type, exactly
  // as the product form does it — so the retail-price field shows when needed.
  const isThirdSchedule = form.sale_type === "3rd Schedule Goods";

  // FBR sale types, grouped (common first, then specialised) — same shape as
  // the product form's dropdown.
  const saleTypeGroups = useMemo(() => {
    const all = saleTypes.data ?? [];
    return {
      common: all.filter((s) => s.group === "common"),
      specialised: all.filter((s) => s.group === "specialised"),
    };
  }, [saleTypes.data]);

  // UoM options deduped by the real FBR unit, shown by friendly label — the
  // identical derivation the product form uses, kept in sync intentionally.
  const uomOptions = useMemo(() => {
    const rows = uoms.data ?? [];
    const seen = new Map<string, { code: string; label: string }>();
    for (const u of rows) {
      const fbr = u.fbr_uom || u.name_en;
      const label = u.fbr_uom_label || fbr;
      if (!seen.has(fbr)) seen.set(fbr, { code: u.code, label });
    }
    const list = Array.from(seen.values());
    const PCS = "Numbers, pieces, units";
    list.sort((a, b) => {
      if (a.label === PCS) return -1;
      if (b.label === PCS) return 1;
      return a.label.localeCompare(b.label);
    });
    return list;
  }, [uoms.data]);

  const codeToOptionCode = useMemo(() => {
    const rows = uoms.data ?? [];
    const repByFbr = new Map<string, string>();
    for (const u of rows) {
      const fbr = u.fbr_uom || u.name_en;
      if (!repByFbr.has(fbr)) repByFbr.set(fbr, u.code);
    }
    const m = new Map<string, string>();
    for (const u of rows) {
      const fbr = u.fbr_uom || u.name_en;
      const rep = repByFbr.get(fbr);
      if (rep) m.set(u.code, rep);
    }
    return m;
  }, [uoms.data]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Send only the FBR-identity fields. retail_price is only meaningful for
    // 3rd-Schedule goods; send it (or null) so the server-side coupling check
    // (3rd-Schedule requires retail_price > 0) sees a consistent value.
    try {
      await update.mutateAsync({
        id: stock.product,
        description: form.description,
        hs_code: form.hs_code || null,
        uom: form.uom,
        sale_type: form.sale_type,
        sro_schedule_no: form.sro_schedule_no,
        sro_item_serial_no: form.sro_item_serial_no,
        tax_rate: form.tax_rate || null,
        retail_price: isThirdSchedule ? form.retail_price || null : null,
      } as never);
      toast.show({ message: "FBR details saved to the product.", variant: "success" });
      onSaved?.();
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <form
      onSubmit={save}
      className="grid grid-cols-1 gap-3 rounded-md border bg-muted/30 p-4 sm:grid-cols-2"
    >
      <div className="sm:col-span-2">
        <p className="text-xs text-muted-foreground">
          These fields are the product's FBR fiscal identity — editing them here
          updates the product everywhere it's used (this is the single source of
          truth, not a per-warehouse copy).
        </p>
      </div>

      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor={`fbr-desc-${stock.id}`}>Product description</Label>
        <Input
          id={`fbr-desc-${stock.id}`}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          placeholder="Optional description shown on the product"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-hs-${stock.id}`}>HS code *</Label>
        <HsCodePicker
          id={`fbr-hs-${stock.id}`}
          value={form.hs_code}
          onChange={(code) => set("hs_code", code)}
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-uom-${stock.id}`}>Unit of measure *</Label>
        <Select
          id={`fbr-uom-${stock.id}`}
          value={codeToOptionCode.get(form.uom) ?? form.uom}
          onChange={(e) => set("uom", e.target.value)}
          required
        >
          <option value="">— Select —</option>
          {uomOptions.map((o) => (
            <option key={o.code} value={o.code}>{o.label}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-sro-${stock.id}`}>SRO schedule (optional)</Label>
        <Input
          id={`fbr-sro-${stock.id}`}
          value={form.sro_schedule_no}
          onChange={(e) => set("sro_schedule_no", e.target.value)}
          placeholder="e.g. EIGHTH SCHEDULE Table 1"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-sroitem-${stock.id}`}>SRO item serial no (optional)</Label>
        <Input
          id={`fbr-sroitem-${stock.id}`}
          value={form.sro_item_serial_no}
          onChange={(e) => set("sro_item_serial_no", e.target.value)}
          placeholder="e.g. 70"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-tax-${stock.id}`}>Tax rate</Label>
        <Select
          id={`fbr-tax-${stock.id}`}
          value={form.tax_rate}
          onChange={(e) => set("tax_rate", e.target.value)}
        >
          <option value="">— None —</option>
          {taxRates.data?.results.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`fbr-saletype-${stock.id}`}>FBR sale type</Label>
        <Select
          id={`fbr-saletype-${stock.id}`}
          value={form.sale_type}
          onChange={(e) => set("sale_type", e.target.value)}
        >
          {saleTypeGroups.common.length > 0 && (
            <optgroup label="Common">
              {saleTypeGroups.common.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </optgroup>
          )}
          {saleTypeGroups.specialised.length > 0 && (
            <optgroup label="Specialised / sector-specific">
              {saleTypeGroups.specialised.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </optgroup>
          )}
        </Select>
      </div>

      {isThirdSchedule && (
        <div className="space-y-1.5">
          <Label htmlFor={`fbr-retail-${stock.id}`}>Retail price *</Label>
          <NumberInput
            id={`fbr-retail-${stock.id}`}
            mode="decimal"
            value={form.retail_price}
            onChange={(v) => set("retail_price", v)}
          />
          <p className="text-xs text-muted-foreground">
            3rd-Schedule goods are taxed on the printed retail price — required.
          </p>
        </div>
      )}

      <div className="flex items-center gap-3 sm:col-span-2">
        <Button type="submit" loading={update.isPending}>
          {update.isPending ? "Saving…" : "Save Details"}
        </Button>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </form>
  );
}
