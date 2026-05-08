import { Check, Printer, ShoppingCart } from "lucide-react";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

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

  useEffect(() => {
    const t = window.setTimeout(() => navigate("/sale", { replace: true }), 8000);
    return () => window.clearTimeout(t);
  }, [navigate]);

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

        <div className="mt-2 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
          FBR pending — submission lands in Phase 4
        </div>

        <div className="mt-6 grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (s.invoice_id) {
                window.api.printer.print({
                  // Receipt re-render uses the persisted local row
                  business_name: "(reprint)",
                  branch_name: "(reprint)",
                  ntn: "(reprint)",
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
          Returns to a new sale automatically in 8 seconds.
        </p>
      </div>
    </div>
  );
}
