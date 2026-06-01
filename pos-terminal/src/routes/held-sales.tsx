import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore, type CartLine } from "@/stores/sale";

import type { PosInvoiceRow } from "../../electron/preload";

export default function HeldSalesRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const toast = useToast();
  const [rows, setRows] = useState<PosInvoiceRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    void window.api.sales.list({ held: true }).then(setRows);
  }, []);

  /**
   * Recall flow:
   *   1. Fetch the held invoice + items from local SQLite.
   *   2. Hydrate the in-memory sale store via loadFromHold.
   *   3. Mark the DB row recalled (is_held=0). We keep the row briefly
   *      so a crash mid-recall leaves an auditable trail.
   *   4. Delete the held row — once the cart is in memory we don't
   *      need the placeholder. The next checkout creates a fresh row
   *      with a new client_uuid + local_invoice_number that DOES
   *      enqueue to the backend (see electron/db/sales.ts).
   *   5. Navigate back to the till.
   */
  async function recall(row: PosInvoiceRow) {
    setBusyId(row.id);
    try {
      const detail = await window.api.sales.get(row.id);
      if (!detail) {
        toast.show({
          message: t("held_sales.missing", "That held sale is no longer available."),
          variant: "warning",
        });
        // Refresh the list — likely deleted by another tab/window.
        setRows(await window.api.sales.list({ held: true }));
        return;
      }
      const lines: CartLine[] = detail.items.map((it) => ({
        id: it.id,
        product_id: it.product_id,
        product_name: it.product_name,
        product_sku: it.product_sku,
        uom_code: it.uom_code,
        hs_code: it.hs_code,
        quantity: it.quantity,
        unit_price: it.unit_price,
        discount_pct: it.discount_pct,
        discount_amount: it.discount_amount,
        tax_rate: it.tax_rate,
        // The local schema doesn't store is_taxable as a flag — we
        // infer it from the rate. Zero-rate lines are not taxable;
        // any positive rate is. Matches what quoteCart expects.
        is_taxable: Number(it.tax_rate) > 0,
        notes: it.notes ?? undefined,
      }));
      useSaleStore.getState().loadFromHold({
        clientUuid: row.client_uuid,
        lines,
        customer: null,           // customer block isn't carried in V1 hold
        cartDiscountPct: "0",
      });
      await window.api.sales.recall(row.id);
      await window.api.sales.deleteHeld(row.id);
      toast.show({
        message: t("held_sales.recalled", "Recalled “{{label}}”.", {
          label: row.held_label ?? row.local_invoice_number,
        }),
        variant: "success",
      });
      navigate("/sale");
    } catch (err) {
      console.error("Recall failed:", err);
      toast.show({
        message: t("held_sales.recall_error", "Could not recall — please try again."),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-muted/30 p-4">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center self-start text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> {t("common.back")}
      </button>

      <h1 className="mt-3 text-xl font-semibold">{t("held_sales.title")}</h1>

      <div className="mt-4 rounded-md border bg-background">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {t("held_sales.no_held")}
          </div>
        ) : (
          <ul className="divide-y" aria-label={t("held_sales.title")}>
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-medium">
                    {r.held_label ?? t("held_sales.unlabelled", "(unlabelled)")}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {r.local_invoice_number} · Rs {r.grand_total}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === r.id}
                  onClick={() => void recall(r)}
                >
                  {busyId === r.id
                    ? t("held_sales.recalling", "Recalling…")
                    : t("held_sales.recall")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
