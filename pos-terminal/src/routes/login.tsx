import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { LanguageToggle } from "@/components/LanguageToggle";
import { PinDots } from "@/components/pin/PinDots";
import { PinKeypad } from "@/components/pin/PinKeypad";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/session";

import type { AuthResponse } from "@pos/shared/types";

const BRANCH_NAME = import.meta.env.VITE_BRANCH_NAME ?? "—";
const TERMINAL_NAME = import.meta.env.VITE_TERMINAL_NAME ?? "Terminal";
const PIN_LEN_MIN = 4;
const PIN_LEN_MAX = 6;

export default function LoginRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const signIn = useSessionStore((s) => s.signIn);

  // Phase 0 simplification: ask the cashier to identify themselves by email
  // before tapping their PIN. In Phase 3 we cache assigned cashiers in
  // SQLite and show a name picker per SCREENS.md §1.
  const [email, setEmail] = useState("");
  const [pin, setPin] = useState("");
  const [shake, setShake] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (pin.length < PIN_LEN_MIN || submitting || !email) return;

    let cancelled = false;
    void (async () => {
      setSubmitting(true);
      try {
        const resp = await api<AuthResponse>(
          "/auth/pin-login/",
          { method: "POST", body: JSON.stringify({ email: email.trim(), pin }) },
          { auth: false },
        );
        if (cancelled) return;
        signIn(resp);
        navigate("/sale", { replace: true });
      } catch (err) {
        if (cancelled) return;
        setShake(true);
        window.setTimeout(() => setShake(false), 400);
        if (err instanceof ApiError && err.status === 400) {
          setError(t("login.invalid_credentials"));
        } else if (err instanceof ApiError && err.status === 429) {
          setError(t("login.too_many_attempts", "Too many attempts. Try again in a few minutes."));
        } else {
          setError(t("login.network_error", "Could not sign in. Check the network."));
        }
        setPin("");
      } finally {
        if (!cancelled) setSubmitting(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // We submit on every PIN-length change ≥ min; the deps below capture it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pin]);

  const onDigit = (d: string) => {
    setError(null);
    setPin((curr) => (curr.length >= PIN_LEN_MAX ? curr : curr + d));
  };
  const onBackspace = () => {
    setError(null);
    setPin((curr) => curr.slice(0, -1));
  };
  const onClear = () => {
    setError(null);
    setPin("");
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <div className="absolute right-4 top-4">
        <LanguageToggle />
      </div>
      <div
        className={cn(
          "w-full max-w-sm rounded-2xl border bg-background p-6 shadow-sm",
          shake && "animate-shake",
        )}
      >
        <div className="mb-1 text-center text-xs uppercase tracking-wide text-muted-foreground">
          {BRANCH_NAME} · {TERMINAL_NAME}
        </div>
        <div className="mb-6 text-center text-lg font-semibold">{t("login.title")}</div>

        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("login.email")}
          autoComplete="email"
          aria-label={t("login.email")}
          className="mb-6 h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />

        <PinDots length={pin.length} className="mb-6" />

        <PinKeypad
          onDigit={onDigit}
          onBackspace={onBackspace}
          onClear={onClear}
          disabled={submitting}
        />

        <div className="mt-4 min-h-[1.25rem] text-center text-sm text-destructive">
          {error}
        </div>
      </div>
    </div>
  );
}
