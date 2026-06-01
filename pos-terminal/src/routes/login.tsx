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
// PINs are exactly 6 digits — fixed length, no Enter button, auto-submit
// on the 6th digit. The backend serializer enforces /^\d{6}$/; the
// Django admin's "Set PIN" form enforces the same. Keep these three
// sites in lockstep.
//
// History: this used to be a 4-6 range with auto-submit at 4. That
// silently broke 6-digit PINs because the terminal posted the partial
// 4-digit value, the backend rejected it, the field cleared on error,
// and digits 5+6 landed in an empty field — making 6-digit PINs
// effectively un-loggable. Hence the fixed length.
const PIN_LENGTH = 6;

/**
 * Pull a human-readable error string out of a DRF error body. DRF can
 * return {"detail": "..."} (auth errors) OR {"non_field_errors": [...]}
 * (validation errors) OR {"<field>": [...]}.  Returns the first string
 * it finds, or null.
 */
function extractDetail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.detail === "string") return b.detail;
  if (Array.isArray(b.non_field_errors) && b.non_field_errors.length > 0) {
    const first = b.non_field_errors[0];
    if (typeof first === "string") return first;
  }
  // First field-level error.
  for (const v of Object.values(b)) {
    if (Array.isArray(v) && typeof v[0] === "string") return v[0];
    if (typeof v === "string") return v;
  }
  return null;
}

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
    // Auto-submit only when the PIN reaches its fixed length. Anything
    // shorter is treated as still-being-typed.
    if (pin.length !== PIN_LENGTH || submitting || !email) return;

    let cancelled = false;
    void (async () => {
      setSubmitting(true);
      try {
        // Normalize on the client so common typing accidents don't
        // turn into "invalid credentials": leading/trailing whitespace
        // from copy-paste, an autocapitalized first letter on touch
        // keyboards, etc. The backend lowercases too as defense in
        // depth, but doing it here also shows the cleaned value in
        // any error/log path.
        const normalizedEmail = email.trim().toLowerCase();
        const resp = await api<AuthResponse>(
          "/auth/pin-login/",
          { method: "POST", body: JSON.stringify({ email: normalizedEmail, pin }) },
          { auth: false },
        );
        if (cancelled) return;
        signIn(resp);
        navigate("/sale", { replace: true });
      } catch (err) {
        if (cancelled) return;
        setShake(true);
        window.setTimeout(() => setShake(false), 400);
        // Verbose console log so DevTools tells us what really came
        // back from the server. Helps trace "PIN works in curl but
        // not from the terminal" mysteries without backend log access.
        // eslint-disable-next-line no-console
        console.error("[login] error:", err);
        if (err instanceof ApiError && err.status === 400) {
          // Surface the backend's reason in dev so a stale autofill
          // or wrong field doesn't masquerade as "invalid PIN".
          const detail = extractDetail(err.data);
          setError(detail
            ? `${t("login.invalid_credentials")} (${detail})`
            : t("login.invalid_credentials"));
        } else if (err instanceof ApiError && err.status === 429) {
          setError(t("login.too_many_attempts", "Too many attempts. Try again in a few minutes."));
        } else if (err instanceof ApiError) {
          // 401, 403, 404, 5xx — not a bad credential per se. Don't
          // mislabel as such.
          setError(t("login.network_error", "Could not sign in (HTTP {{status}}). Check the network.", { status: err.status }));
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
    setPin((curr) => (curr.length >= PIN_LENGTH ? curr : curr + d));
  };
  const onBackspace = () => {
    setError(null);
    setPin((curr) => curr.slice(0, -1));
  };
  const onClear = () => {
    setError(null);
    setPin("");
  };

  // Hardware-keyboard support. Cashiers using a desktop POS with a USB
  // keyboard expect to type the PIN, not click the on-screen keypad.
  //
  // We listen at window level (instead of an <input> bound to `pin`)
  // because the PIN itself is rendered as a row of dots, not an input
  // — there's nothing for the keyboard to focus on. The handler is
  // skipped while the email <input> has focus so typing the email
  // doesn't pour digits into the PIN.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Don't hijack keystrokes while the email field is being typed,
      // and don't fight modifier shortcuts (Cmd-R, Ctrl-V, etc.).
      const target = e.target as HTMLElement | null;
      if (target && target.tagName === "INPUT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Numpad digits report `e.key` as the digit too, so /^\d$/ covers
      // both the top row and the numpad uniformly.
      if (/^\d$/.test(e.key)) {
        e.preventDefault();
        onDigit(e.key);
        return;
      }
      if (e.key === "Backspace") {
        e.preventDefault();
        onBackspace();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        onClear();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // The handlers above are defined fresh each render but only read
    // setState setters (stable refs), so we don't need them in deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="relative flex h-full items-center justify-center overflow-y-auto bg-muted/40 p-4">
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
          // On touch keyboards the first letter gets auto-capitalized
          // by default and autocorrect can mangle the local-part. Both
          // produce spurious "invalid credentials" errors against an
          // otherwise correct account. Lower-casing in onSubmit also
          // helps, but disabling these at input time matches what the
          // operator typed and avoids the cosmetic mismatch.
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          inputMode="email"
          // Focus on mount so the cashier can start typing the email
          // immediately. Once they tab/click away from this input, the
          // window-level keydown listener takes over for PIN digits.
          autoFocus
          aria-label={t("login.email")}
          className="mb-6 h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />

        <PinDots length={pin.length} capacity={PIN_LENGTH} className="mb-6" />

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
