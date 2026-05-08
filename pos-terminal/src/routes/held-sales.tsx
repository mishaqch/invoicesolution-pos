import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

import type { PosInvoiceRow } from "../../electron/preload";

export default function HeldSalesRoute() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<PosInvoiceRow[]>([]);

  useEffect(() => {
    void window.api.sales.list({ held: true }).then(setRows);
  }, []);

  return (
    <div className="min-h-screen bg-muted/30 p-4">
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> Back
      </button>

      <h1 className="mt-3 text-xl font-semibold">Held sales</h1>
      <p className="text-sm text-muted-foreground">
        Phase 2 ships in-memory holds; persisted holds via the sync engine
        land in Phase 3. This list reflects locally-stored holds.
      </p>

      <div className="mt-4 rounded-md border bg-background">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No held sales.
          </div>
        ) : (
          <ul className="divide-y">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-medium">{r.held_label ?? "(unlabelled)"}</div>
                  <div className="text-xs text-muted-foreground">
                    {r.local_invoice_number} · Rs {r.grand_total}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await window.api.sales.recall(r.id);
                    navigate("/sale");
                  }}
                >
                  Recall
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
