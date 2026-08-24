import { Check, Printer, ShoppingCart } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useFbrConfirmation } from "@/features/sale/useFbrConfirmation";
import { useTerminalFiscalize } from "@/features/sale/useTerminalFiscalize";
import { printInvoiceById } from "@/features/printing/printInvoice";
import { rs } from "@/lib/money";
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
  const { t } = useTranslation();
  const { state } = useLocation();
  const s = (state as State) ?? {};

  const [fbrNo, setFbrNo] = useState<string | null>(null);
  const toast = useToast();

  // Non-fiscal tenants (e.g. TDCP — tax collected by PRA, no FBR integration
  // yet) have no FBR flow: don't poll FBR and don't show any "Submitting to
  // FBR…" badge. Fiscal tenants are unchanged. (When PRA is wired for TDCP
  // later, this becomes an authority-aware label.)
  const tenant = useSessionStore((s) => s.tenant);
  const isFiscal = tenant?.fbr_connection_type !== "none";

  // Persist the FBR number locally, then reprint with the QR. Shared by both
  // the active SDC path and the passive cloud-confirmation fallback.
  const persistAndReprint = (fbrInvoiceNumber: string, qrPayload: string | null) => {
    setFbrNo(fbrInvoiceNumber);
    if (!s.invoice_id) return;
    void window.api.sales
      .setFbrFields({
        invoice_id: s.invoice_id,
        fbr_invoice_number: fbrInvoiceNumber,
        fbr_qr_payload: qrPayload,
        fbr_validated_at: new Date().toISOString(),
      })
      .catch(() => {})
      .then(() => printInvoiceById(s.invoice_id!).catch(() => {}));
  };

  // PRIMARY path: the terminal drives fiscalization through its local FBR SDC
  // (localhost:8524) as soon as the invoice reaches the server — fast, since
  // the SDC is on the LAN. The receipt reprints with the QR once verified.
  useTerminalFiscalize({
    // Non-fiscal tenant → pass undefined so the hook no-ops (no FBR polling).
    invoiceId: isFiscal ? s.invoice_id : undefined,
    onFiscalized: (num) => persistAndReprint(num, null),
    // onDeferred: no-op — the fallback poll below covers offline/SDC-down.
  });

  // FALLBACK path: if the terminal couldn't fiscalize (offline, SDC down, or a
  // DI-API/non-SDC tenant), keep polling the cloud, which fiscalizes its own
  // way. Slower interval; reprints with QR when the number eventually arrives.
  useFbrConfirmation({
    // Non-fiscal tenant → pass undefined so the hook no-ops (no cloud FBR poll).
    invoiceId: isFiscal ? s.invoice_id : undefined,
    onValid: (inv) => {
      if (inv.fbr_invoice_number) {
        persistAndReprint(inv.fbr_invoice_number, inv.fbr_qr_payload);
      }
    },
  });

  // Auto-advance — slightly longer if we're still waiting for FBR confirm.
  // Non-fiscal tenants never wait on FBR, so advance on the short timer.
  useEffect(() => {
    const ms = fbrNo || !isFiscal ? 5000 : 12_000;
    const t = window.setTimeout(() => navigate("/sale", { replace: true }), ms);
    return () => window.clearTimeout(t);
  }, [navigate, fbrNo, isFiscal]);

  return (
    <div className="flex h-full items-center justify-center bg-success-soft p-8">
      <div className="w-full max-w-md rounded-2xl border bg-background p-8 text-center shadow-sm">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-success text-success-foreground">
          <Check className="h-10 w-10" strokeWidth={3} aria-hidden />
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">{t("success.title")}</h1>
        <div className="mt-2 font-mono text-sm text-muted-foreground">{s.local}</div>

        <dl className="mx-auto mt-6 grid max-w-xs grid-cols-2 gap-y-1 text-sm">
          <dt className="text-muted-foreground">{t("sale.total")}</dt>
          <dd className="text-right font-mono">Rs {rs(s.grand)}</dd>
          <dt className="text-muted-foreground">{t("payment.amount_tendered")}</dt>
          <dd className="text-right font-mono">Rs {rs(s.tendered)}</dd>
          <dt className="text-muted-foreground">{t("payment.change")}</dt>
          <dd className="text-right font-mono">Rs {rs(s.change)}</dd>
        </dl>

        {/* FBR status badge only for fiscal tenants. Non-fiscal (TDCP) has no
            FBR flow, so no "Submitting to FBR…" here. */}
        {isFiscal && (
          <div
            className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs ${
              fbrNo
                ? "bg-success-soft text-success-soft-foreground"
                : "bg-warning-soft text-warning-soft-foreground"
            }`}
          >
            {fbrNo ? `FBR #${fbrNo.slice(0, 16)}…` : t("success.fbr_pending")}
          </div>
        )}

        <div className="mt-6 grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              if (!s.invoice_id) return;
              const res = await printInvoiceById(s.invoice_id);
              if (res.notFound) {
                toast.show({
                  message: t("print.not_found", "Receipt data is no longer available."),
                  variant: "warning",
                });
              } else if (!res.success) {
                toast.show({
                  message: res.fallbackPath
                    ? t(
                        "print.fallback",
                        "No printer configured — receipt saved to disk: {{path}}",
                        { path: res.fallbackPath },
                      )
                    : t("print.error", "Printer error: {{reason}}", {
                        reason: res.reason ?? "unknown",
                      }),
                  variant: "warning",
                });
              } else {
                toast.show({
                  message: t("print.sent", "Receipt sent to the printer."),
                  variant: "success",
                });
              }
            }}
          >
            <Printer className="mr-1 h-4 w-4" /> {t("success.print_receipt")}
          </Button>
          <Button onClick={() => navigate("/sale", { replace: true })}>
            <ShoppingCart className="mr-1 h-4 w-4" /> {t("success.new_sale")}
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          {t("success.auto_return", "Returns to a new sale in {{seconds}}s.", {
            seconds: fbrNo ? 5 : 12,
          })}
        </p>
      </div>
    </div>
  );
}
