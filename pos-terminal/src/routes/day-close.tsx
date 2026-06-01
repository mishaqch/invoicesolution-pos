import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { NumberInput } from "@/components/ui/number-input";
import { ApiError, api } from "@/lib/api";
import { Money } from "@/lib/money";
import { useSessionStore } from "@/stores/session";
import { usePosContext } from "@/features/sale/usePosContext";

type Step = "summary" | "count" | "reason";

export default function DayCloseRoute() {
  const navigate = useNavigate();
  const ctx = usePosContext();
  const logout = useSessionStore((s) => s.logout);

  const [step, setStep] = useState<Step>("summary");
  const [declared, setDeclared] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totals, setTotals] = useState<{ total_sales: string }>({ total_sales: "0" });

  useEffect(() => {
    if (!ctx.session) return;
    void window.api.session.totals(ctx.session.id).then(setTotals);
  }, [ctx.session]);

  if (ctx.loading || !ctx.terminal) return <Splash msg="Loading…" />;
  if (!ctx.session) {
    return <Splash msg="No session is open." variant="error" />;
  }

  const opened = Money.fromStr(ctx.session.opened_with_amount);
  const cashSales = Money.fromStr(totals.total_sales);
  const expected = opened.add(cashSales);
  const declaredM = declared ? Money.fromStr(declared) : Money.zero();
  const variance = declaredM.sub(expected);

  async function close() {
    if (!ctx.session) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/sales/cash-sessions/${ctx.session.id}/close/`, {
        method: "POST",
        body: JSON.stringify({
          declared_amount: declaredM.toStorageString(),
          variance_reason: reason,
        }),
      });
      await window.api.session.close(ctx.session.id, {
        closed_at: new Date().toISOString(),
        closed_with_amount: declaredM.toStorageString(),
        expected_amount: expected.toStorageString(),
        variance: variance.toStorageString(),
        variance_reason: reason,
      });
      // Lock the terminal: log out the cashier.
      logout();
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? `API ${err.status}` : "Close failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-muted/30 p-4">
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> Back
      </button>

      <h1 className="mt-3 text-2xl font-semibold tracking-tight">Day close</h1>

      <div className="mt-4 grid w-full max-w-md gap-3">
        <div className="rounded-md border bg-background p-4">
          <div className="text-sm font-semibold">Summary</div>
          <Row label="Opening cash" value={`Rs ${opened.display()}`} />
          <Row label="Cash sales" value={`Rs ${cashSales.display()}`} />
          <Row label="Expected" value={`Rs ${expected.display()}`} />
        </div>

        {step !== "summary" && (
          <div className="rounded-md border bg-background p-4">
            <div className="text-sm font-semibold">Count cash</div>
            <label className="mt-2 block text-sm">Declared cash in drawer</label>
            <NumberInput
              mode="decimal"
              value={declared}
              onChange={setDeclared}
              className="mt-1 h-10 font-mono text-base"
              placeholder={expected.display()}
              aria-label="Declared cash in drawer"
            />
            <Row
              label="Variance"
              value={`${variance.isNegative() ? "Rs " + variance.display() : "+ Rs " + variance.display()}`}
              muted={!variance.isZero()}
            />
          </div>
        )}

        {step === "reason" && !variance.isZero() && (
          <div className="rounded-md border bg-background p-4">
            <div className="text-sm font-semibold">Variance reason</div>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Explain the over/short…"
            />
          </div>
        )}

        {/* Step-driven action bar. Each step shows exactly ONE primary
            button so the cashier can't fire two intents at once.
              summary → "Count cash"
              count   → "Close day"   (variance == 0)
                      → "Add reason"  (variance != 0)
              reason  → "Close day"
            Prior implementation had two overlapping branches that
            BOTH rendered on step="count" when variance was zero,
            producing duplicate "Close day" buttons. */}
        <div className="flex justify-end gap-2">
          {step === "summary" && (
            <Button onClick={() => setStep("count")}>Count cash</Button>
          )}
          {step === "count" && variance.isZero() && (
            <Button onClick={close} disabled={busy || !declared}>
              {busy ? "Closing…" : "Close day"}
            </Button>
          )}
          {step === "count" && !variance.isZero() && (
            <Button onClick={() => setStep("reason")} disabled={!declared}>
              Add reason
            </Button>
          )}
          {step === "reason" && (
            <Button onClick={close} disabled={busy || !declared || !reason.trim()}>
              {busy ? "Closing…" : "Close day"}
            </Button>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </div>
  );
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="mt-1 flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-mono ${muted ? "text-warning-soft-foreground" : ""}`}>{value}</span>
    </div>
  );
}

function Splash({
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
