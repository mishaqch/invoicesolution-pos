import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { NumberInput } from "@/components/ui/number-input";
import { ApiError, api } from "@/lib/api";
import { newClientUuid } from "@/lib/uuid";
import { useSessionStore } from "@/stores/session";
import { usePosContext } from "@/features/sale/usePosContext";

export default function DayOpenRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const ctx = usePosContext();
  const user = useSessionStore((s) => s.user);

  const [opening, setOpening] = useState("5000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (ctx.loading) {
    return <FullScreen msg={t("common.loading")} />;
  }
  if (ctx.error) {
    return <FullScreen msg={ctx.error} variant="error" />;
  }
  if (!ctx.branch || !ctx.terminal) {
    return <FullScreen msg={t("day_open.no_terminal", "No branch/terminal configured.")} variant="error" />;
  }
  if (ctx.session) {
    // Already open — straight to sale.
    navigate("/sale", { replace: true });
    return null;
  }

  async function open() {
    if (!ctx.branch || !ctx.terminal || !user) return;
    setBusy(true);
    setError(null);
    try {
      const session = await api<{ id: string; opened_at: string }>(
        "/sales/cash-sessions/open/",
        {
          method: "POST",
          body: JSON.stringify({
            branch: ctx.branch.id,
            terminal: ctx.terminal.id,
            opening_amount: opening,
          }),
        },
      );
      // Mirror the open session locally.
      await window.api.session.open({
        id: session.id,
        branch_id: ctx.branch.id,
        terminal_id: ctx.terminal.id,
        cashier_id: user.id,
        opened_at: session.opened_at,
        opened_with_amount: opening,
        closed_at: null,
        closed_with_amount: null,
        expected_amount: null,
        variance: null,
        variance_reason: null,
        total_sales: "0",
        cash_in: "0",
        cash_out: "0",
        status: "open",
      });
      // Sanity: also enqueue an outbound row in case the POST gets retried.
      await window.api.queue.enqueue({
        client_uuid: newClientUuid(),
        entity_type: "cash_session",
        entity_id: session.id,
        action: "open",
        payload: { id: session.id },
      });
      navigate("/sale", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? `API ${err.status}` : t("day_open.failed", "Failed to open session."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center overflow-y-auto bg-muted/40 p-4">
      <div className="w-full max-w-sm rounded-2xl border bg-background p-6 shadow-sm">
        <div className="mb-1 text-center text-xs uppercase tracking-wide text-muted-foreground">
          {ctx.branch.name} · {ctx.terminal.name}
        </div>
        <div className="mb-6 text-center text-lg font-semibold">
          {t("day_open.greeting", "Good morning{{comma}}{{name}}.", {
            comma: user ? ", " : "",
            name: user?.full_name.split(" ")[0] ?? "",
          })}
        </div>

        <label className="text-sm font-medium">{t("day_open.opening_float")}</label>
        <NumberInput
          mode="decimal"
          value={opening}
          onChange={setOpening}
          aria-label={t("day_open.opening_float")}
          className="mt-1 h-10 text-base"
        />
        <p className="mt-2 text-xs text-muted-foreground">
          {t("day_open.opening_help", "Enter the cash float you are starting the day with.")}
        </p>

        <Button className="mt-6 w-full" onClick={open} disabled={busy}>
          {busy ? t("day_open.opening", "Opening…") : t("day_open.title")}
        </Button>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </div>
    </div>
  );
}

function FullScreen({
  msg,
  variant = "info",
}: {
  msg: string;
  variant?: "info" | "error";
}) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-sm">
      <div className={variant === "error" ? "text-destructive" : "text-muted-foreground"}>
        {msg}
      </div>
    </div>
  );
}
