import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

import type { PosInvoiceRow } from "../../electron/preload";

export default function HeldSalesRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
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
        <ArrowLeft className="mr-1 h-4 w-4" /> {t("common.back")}
      </button>

      <h1 className="mt-3 text-xl font-semibold">{t("held_sales.title")}</h1>

      <div className="mt-4 rounded-md border bg-background">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {t("held_sales.no_held")}
          </div>
        ) : (
          <ul className="divide-y">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-medium">{r.held_label ?? t("held_sales.unlabelled", "(unlabelled)")}</div>
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
                  {t("held_sales.recall")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
