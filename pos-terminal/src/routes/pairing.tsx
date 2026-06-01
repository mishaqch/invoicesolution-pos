import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { LanguageToggle } from "@/components/LanguageToggle";

/**
 * First-launch pairing screen.
 *
 * A fresh terminal has no identity. The owner creates this terminal in
 * admin-web (Branches → Terminals) and reads the cashier a one-time pairing
 * code; the cashier types it here. On success the terminal is bound to that
 * branch + terminal forever (until explicitly unpaired in Hardware) and we
 * proceed to cashier login.
 */
export default function PairingRoute() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paired, setPaired] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || code.trim().length < 8) return;
    setSubmitting(true);
    setError(null);
    const res = await window.api.pairing.pair(code);
    setSubmitting(false);
    if (res.ok && res.identity) {
      setPaired(`${res.identity.branchName} · ${res.identity.terminalName}`);
      // Brief confirmation, then on to login.
      window.setTimeout(() => navigate("/login", { replace: true }), 1200);
    } else {
      setError(res.error ?? "Pairing failed. Check the code and try again.");
    }
  };

  return (
    <div className="relative flex h-full items-center justify-center bg-background">
      <div className="absolute right-4 top-4">
        <LanguageToggle />
      </div>
      <div className="w-full max-w-md px-6">
        <div className="mb-8 text-center">
          <div className="text-3xl font-semibold tracking-tight">InvoiceSolution</div>
          <div className="mt-2 text-sm text-muted-foreground">
            Connect this terminal to your branch
          </div>
        </div>

        {paired ? (
          <div className="rounded-lg border border-green-600/30 bg-green-600/10 p-6 text-center">
            <div className="text-lg font-medium text-green-700">Paired successfully</div>
            <div className="mt-1 text-sm text-muted-foreground">{paired}</div>
            <div className="mt-3 text-xs text-muted-foreground">Continuing to sign in…</div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="pairing-code">
                Pairing code
              </label>
              <input
                id="pairing-code"
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="ABCD-EFGH"
                spellCheck={false}
                autoCapitalize="characters"
                className="w-full rounded-md border border-input bg-transparent px-4 py-3 text-center font-mono text-2xl tracking-widest outline-none focus:ring-2 focus:ring-ring"
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Get this code from your owner in the admin web
                (Branches → Terminals → this terminal).
              </p>
            </div>

            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || code.trim().length < 8}
              className="w-full rounded-md bg-primary py-3 font-medium text-primary-foreground disabled:opacity-50"
            >
              {submitting ? "Connecting…" : "Connect terminal"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
