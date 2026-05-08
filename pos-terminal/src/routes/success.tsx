import { Check, Printer, ShoppingCart } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useFbrConfirmation } from "@/features/sale/useFbrConfirmation";
import { useSessionStore } from "@/stores/session";

interface State {
  invoice_id?: string;
  local?: string;
  grand?: string;
  tendered?: string;
  change?: string;
}

export default function SuccessRoute() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const s = (state as State) ?? {};

  const [fbrNo, setFbrNo] = useState<string | null>(null);
  const tenant = useSessionStore((st) => st.tenant);

  useFbrConfirmation({
    invoiceId: s.invoice_id,
    onValid: (inv) => {
      setFbrNo(inv.fbr_invoice_number);
      // Best-effort QR re-print. Never blocks the cashier.
      void window.api.printer.print({
        business_name: tenant?.business_name ?? "POS",
        branch_name: "(reprint)",
        ntn: tenant?.ntn ?? "",
        invoice: {
          id: inv.id,
          local_invoice_number: inv.local_invoice_number,
          invoice_date: inv.invoice_date,
          subtotal: "0", discount_total: "0", tax_total: "0",
          grand_total: inv.grand_total,
          paid_total: inv.paid_total,
          change_given: inv.change_given,
          fbr_invoice_number: inv.fbr_invoice_number,
          fbr_qr_payload: inv.fbr_qr_payload,
        } as never,
        items: [],
        payments: [],
        width: 48,
      });
    },
  });

  // Auto-advance — slightly longer if we're still waiting for FBR confirm.
  useEffect(() => {
    const ms = fbrNo ? 5000 : 12_000;
    const t = window.setTimeout(() => navigate("/sale", { replace: true }), ms);
    return () => window.clearTimeout(t);
  }, [navigate, fbrNo]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-green-50 p-8">
      <div className="w-full max-w-md rounded-2xl border bg-background p-8 text-center shadow-sm">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-green-100">
          <Check className="h-10 w-10 text-green-700" strokeWidth={3} />
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Sale complete</h1>
        <div className="mt-2 font-mono text-sm text-muted-foreground">{s.local}</div>

        <dl className="mx-auto mt-6 grid max-w-xs grid-cols-2 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Total</dt>
          <dd className="text-right font-mono">Rs {s.grand}</dd>
          <dt className="text-muted-foreground">Tendered</dt>
          <dd className="text-right font-mono">Rs {s.tendered}</dd>
          <dt className="text-muted-foreground">Change</dt>
          <dd className="text-right font-mono">Rs {s.change}</dd>
        </dl>

        <div
          className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs ${
            fbrNo ? "bg-green-100 text-green-900" : "bg-amber-100 text-amber-900"
          }`}
        >
          {fbrNo ? `FBR #${fbrNo.slice(0, 16)}…` : "FBR pending — submitting…"}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (s.invoice_id) {
                void window.api.printer.print({
                  business_name: tenant?.business_name ?? "(reprint)",
                  branch_name: "(reprint)",
                  ntn: tenant?.ntn ?? "",
                  invoice: { id: s.invoice_id } as never,
                  items: [],
                  payments: [],
                  width: 48,
                });
              }
            }}
          >
            <Printer className="mr-1 h-4 w-4" /> Reprint
          </Button>
          <Button onClick={() => navigate("/sale", { replace: true })}>
            <ShoppingCart className="mr-1 h-4 w-4" /> New sale
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Returns to a new sale automatically in {fbrNo ? "5" : "12"} seconds.
        </p>
      </div>
    </div>
  );
}
