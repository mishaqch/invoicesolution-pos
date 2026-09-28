import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { pinLogin } from "@/api/auth";
import { extractApiErrorMessage } from "@/lib/api";
import { PinPad } from "@/components/auth/PinPad";
import { useAuthStore } from "@/stores/auth";

/** /pin?email=&name= — 6-digit PIN pad; auto-submits at 6 digits. */
export default function PinRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const email = params.get("email") ?? "";
  const name = params.get("name") ?? "";
  const signIn = useAuthStore((s) => s.signIn);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetSignal, setResetSignal] = useState(0);

  async function handleComplete(pin: string) {
    if (!email) {
      navigate("/staff", { replace: true });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await pinLogin({ email, pin });
      signIn({
        access: res.access,
        refresh: res.refresh,
        userName: res.user.full_name || name || res.user.email,
        userEmail: res.user.email,
        role: res.role,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(extractApiErrorMessage(err));
      // Clear the pad so the waiter can retry.
      setResetSignal((n) => n + 1);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-wrap">
      <div className="auth-card">
        <button className="auth-back" type="button" onClick={() => navigate("/staff")}>
          ← Not you? Change name
        </button>
        <h2 className="auth-title">Hi{name ? `, ${name.split(" ")[0]}` : ""}</h2>
        <p className="auth-sub">Enter your 6-digit PIN to start taking orders.</p>

        <PinPad onComplete={handleComplete} submitting={submitting} resetSignal={resetSignal} />

        {error ? (
          <div className="auth-err" role="alert" style={{ textAlign: "center" }}>
            {error}
          </div>
        ) : null}
        {submitting ? (
          <div style={{ display: "grid", placeItems: "center", marginTop: 14 }}>
            <div className="page-spin" role="status" aria-label="Signing in" />
          </div>
        ) : null}
      </div>
    </main>
  );
}
