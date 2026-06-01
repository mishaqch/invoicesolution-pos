import { ArrowLeft, Printer, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/feedback/Toast";
import { printInvoiceById } from "@/features/printing/printInvoice";

import type { PosInvoiceRow, PosSaleItemRow, PosPaymentRow } from "../../electron/preload";

interface InvoiceWithLines {
  invoice: PosInvoiceRow;
  items: PosSaleItemRow[];
  payments: PosPaymentRow[];
}

/**
 * "Today's invoices" — what the cashier sold at this terminal today.
 *
 * Reads from local SQLite via window.api so it works offline. The
 * cashier can filter by invoice number, see the line items via the
 * detail drawer, and reprint a receipt without leaving the POS.
 */
export default function TodayInvoicesRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const toast = useToast();

  const [rows, setRows] = useState<PosInvoiceRow[]>([]);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<InvoiceWithLines | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void window.api.sales
      .list({ limit: 200 })
      .then((all) => {
        const todayPrefix = new Date().toISOString().slice(0, 10);
        setRows(all.filter((r) => r.created_at?.startsWith(todayPrefix)));
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.local_invoice_number.toLowerCase().includes(q) ||
        (r.fbr_invoice_number ?? "").toLowerCase().includes(q),
    );
  }, [rows, query]);

  const totals = useMemo(() => {
    const gross = rows.reduce((acc, r) => acc + Number(r.grand_total ?? "0"), 0);
    return { count: rows.length, gross };
  }, [rows]);

  async function open(id: string) {
    const data = await window.api.sales.get(id);
    if (data) setPicked(data);
  }

  async function reprint(invoice: PosInvoiceRow) {
    const res = await printInvoiceById(invoice.id);
    if (res.notFound) {
      toast.show({
        message: t("print.not_found", "Receipt data is no longer available."),
        variant: "warning",
      });
    } else if (!res.success) {
      toast.show({
        message: res.fallbackPath
          ? t("print.fallback",
              "No printer configured — receipt saved to disk: {{path}}",
              { path: res.fallbackPath })
          : t("print.error", "Printer error: {{reason}}",
              { reason: res.reason ?? "unknown" }),
        variant: "warning",
      });
    } else {
      toast.show({
        message: t("print.sent", "Receipt sent to the printer."),
        variant: "success",
      });
    }
  }

  return (
    // h-full + min-h-0 (instead of min-h-screen) so the inner panes
    // can scroll independently. Without this, the page body grows to
    // fit the detail panel's content and the WHOLE PAGE scrolls
    // (cutting off the right rail). Same pattern as routes/sale.tsx.
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate("/sale", { replace: true })}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> {t("common.back")}
        </button>
        <div className="text-sm font-medium">{t("today_invoices.title", "Today's invoices")}</div>
        <div className="text-xs text-muted-foreground">
          {totals.count} · Rs {totals.gross.toLocaleString("en-PK", { maximumFractionDigits: 0 })}
        </div>
      </header>

      {/* min-h-0 is critical on a flex child whose parent uses flex-col:
          without it, flex-1 won't shrink below the intrinsic content
          height and the inner overflow-y-auto becomes a no-op. */}
      <main className="flex min-h-0 flex-1 overflow-hidden">
        <section className="flex w-2/5 min-h-0 flex-col border-r">
          <div className="border-b p-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder={t("today_invoices.search_placeholder", "Search by invoice #")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label={t("today_invoices.search_placeholder", "Search by invoice #")}
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <p className="p-4 text-sm text-muted-foreground">{t("common.loading")}</p>
            ) : filtered.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">
                {t("today_invoices.empty", "No sales yet today.")}
              </p>
            ) : (
              <ul className="divide-y">
                {filtered.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => open(r.id)}
                      className={`block w-full p-3 text-left text-sm hover:bg-muted ${
                        picked?.invoice.id === r.id ? "bg-muted" : ""
                      }`}
                    >
                      <div className="flex items-baseline justify-between">
                        <span className="font-mono">{r.local_invoice_number}</span>
                        <span className="font-mono">Rs {r.grand_total}</span>
                      </div>
                      <div className="flex items-baseline justify-between text-xs text-muted-foreground">
                        <span>{(r.created_at ?? "").slice(11, 16)}</span>
                        <span className={r.fbr_invoice_number ? "text-success-soft-foreground" : "text-warning-soft-foreground"}>
                          {r.fbr_invoice_number ? `FBR ${r.fbr_invoice_number.slice(0, 12)}…` : t("success.fbr_pending")}
                        </span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Detail pane — gets its own scroll. min-h-0 here lets the
            overflow-y-auto actually clip (same flex/flexbox rule as
            the list pane above). */}
        <section className="min-h-0 flex-1 overflow-y-auto p-4">
          {!picked ? (
            <p className="text-sm text-muted-foreground">
              {t("today_invoices.pick_invoice", "Pick an invoice to view details.")}
            </p>
          ) : (
            <div className="space-y-4">
              <div className="flex items-baseline justify-between">
                <div>
                  <div className="text-xl font-semibold">{picked.invoice.local_invoice_number}</div>
                  <div className="text-xs text-muted-foreground">
                    {(picked.invoice.created_at ?? "").replace("T", " ").slice(0, 16)}
                  </div>
                </div>
                <Button size="sm" onClick={() => reprint(picked.invoice)}>
                  <Printer className="mr-1 h-4 w-4" /> {t("success.print_receipt")}
                </Button>
              </div>

              <div>
                <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">{t("sale.title")}</div>
                <table className="w-full text-sm">
                  <tbody>
                    {picked.items.map((line) => (
                      <tr key={line.id} className="border-b last:border-0">
                        <td className="py-1.5">{line.product_name}</td>
                        <td className="py-1.5 text-right text-muted-foreground">
                          {line.quantity} × Rs {line.unit_price}
                        </td>
                        <td className="py-1.5 text-right font-mono">Rs {line.line_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("sale.subtotal")}</span>
                  <span className="font-mono">Rs {picked.invoice.subtotal}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("sale.tax")}</span>
                  <span className="font-mono">Rs {picked.invoice.tax_total}</span>
                </div>
                <div className="flex justify-between text-base font-semibold">
                  <span>{t("sale.total")}</span>
                  <span className="font-mono">Rs {picked.invoice.grand_total}</span>
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">{t("payment.title")}</div>
                <ul className="space-y-1 text-sm">
                  {picked.payments.map((p) => (
                    <li key={p.id} className="flex justify-between">
                      <span className="capitalize">{p.payment_method.replace(/_/g, " ")}</span>
                      <span className="font-mono">Rs {p.amount}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {picked.invoice.fbr_invoice_number && (
                <div className="rounded-md bg-success-soft p-2 text-xs text-success-soft-foreground">
                  FBR Invoice: <span className="font-mono">{picked.invoice.fbr_invoice_number}</span>
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
