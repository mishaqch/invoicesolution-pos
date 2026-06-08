import { ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import { PinDots } from "@/components/pin/PinDots";
import { PinKeypad } from "@/components/pin/PinKeypad";
import { ApiError, api } from "@/lib/api";

const PIN_LENGTH = 6;

export interface ApprovalRequest {
  /** Short machine action tag for the audit log, e.g. "void_line". */
  action: string;
  /** Human label shown in the modal, e.g. "Remove Coca-Cola 1.5L". */
  label: string;
  /** Extra context recorded in the audit trail (product, qty, amount…). */
  context?: Record<string, unknown>;
  /** Called once a supervisor PIN is verified server-side. */
  onApproved: (by: { role: string; name: string }) => void;
}

/**
 * Supervisor-approval modal. A cashier triggers a restricted till action
 * (void / qty-down / discount / void-sale); a manager/owner types their email
 * + 6-digit PIN, which is VERIFIED SERVER-SIDE (POST /api/auth/supervisor-
 * verify/) — a cashier PIN or wrong-tenant manager is rejected, and the
 * approval is audit-logged. We never approve client-side.
 *
 * Offline policy: server verification is mandatory, so when offline we block
 * with a clear message rather than allow an unverifiable override.
 */
export function SupervisorApproval({
  request,
  onClose,
}: {
  request: ApprovalRequest;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const offline = typeof navigator !== "undefined" && navigator.onLine === false;

  async function submit(finalPin: string) {
    if (submitting) return;
    if (offline) {
      setError("Manager approval needs an internet connection. Try again when online.");
      return;
    }
    if (!email.trim()) {
      setError("Enter the manager's email.");
      setPin("");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api<{ valid: boolean; role: string; supervisor_name: string }>(
        "/auth/supervisor-verify/",
        {
          method: "POST",
          body: JSON.stringify({
            email: email.trim(),
            pin: finalPin,
            action: request.action,
            context: request.context ?? {},
          }),
        },
      );
      if (res.valid) {
        request.onApproved({ role: res.role, name: res.supervisor_name });
        onClose();
      } else {
        setError("Not authorized.");
        setPin("");
      }
    } catch (err) {
      setPin("");
      if (err instanceof ApiError && err.status === 400) {
        setError("Invalid PIN, or this account can't authorize this action.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Wait a moment and try again.");
      } else {
        setError("Couldn't verify — check the connection and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const onKey = (digit: string) => {
    setError(null);
    const next = (pin + digit).slice(0, PIN_LENGTH);
    setPin(next);
    if (next.length === PIN_LENGTH) void submit(next);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-2xl border bg-background p-6 shadow-xl">
        <div className="mb-4 flex items-start justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-500" />
            <h2 className="text-lg font-semibold">Manager approval</h2>
          </div>
          <button onClick={onClose} aria-label="Cancel" className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-4 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{request.label}</span>
          {" "}needs a manager or owner to authorize.
        </p>

        <label className="mb-1 block text-xs font-medium">Manager email</label>
        <input
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setError(null); }}
          placeholder="manager@shop.pk"
          className="mb-4 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />

        <div className="mb-3 flex justify-center">
          <PinDots length={pin.length} capacity={PIN_LENGTH} />
        </div>

        {error && (
          <p className="mb-3 text-center text-sm text-destructive">{error}</p>
        )}
        {offline && !error && (
          <p className="mb-3 text-center text-xs text-amber-600">
            Offline — approval needs an internet connection.
          </p>
        )}

        <PinKeypad
          onDigit={onKey}
          onBackspace={() => { setPin((p) => p.slice(0, -1)); setError(null); }}
          onClear={() => { setPin(""); setError(null); }}
          disabled={submitting || offline}
        />

        <button
          onClick={onClose}
          className="mt-4 w-full rounded-md border py-2 text-sm hover:bg-muted"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
