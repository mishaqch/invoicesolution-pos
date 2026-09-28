import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { pairTerminal } from "@/api/terminals";
import { extractApiErrorMessage } from "@/lib/api";
import { PairingCodeForm } from "@/components/auth/PairingCodeForm";
import { useDeviceStore } from "@/stores/device";

/** /pairing — one-time device pairing with a code from the admin. */
export default function PairingRoute() {
  const navigate = useNavigate();
  const setPaired = useDeviceStore((s) => s.setPaired);
  const deviceFingerprint = useDeviceStore((s) => s.deviceFingerprint);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handlePair(code: string) {
    setSubmitting(true);
    setError(null);
    try {
      const res = await pairTerminal({
        pairing_code: code,
        device_fingerprint: deviceFingerprint,
        // Backend caps os_version at 50 chars; a full userAgent blows past that
        // and fails validation. Send the short platform token, truncated to fit.
        os_version: (navigator.platform || navigator.userAgent || "web").slice(0, 50),
        app_version: "tablet-web",
      });
      setPaired(res);
      navigate("/staff", { replace: true });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-wrap">
      <div className="auth-card">
        <div className="auth-brand">
          <img src="/logo-tdcp.png" alt="TDCP Lake Resort" width={52} height={50} />
          <div>
            <h1>TDCP Lake Resort</h1>
            <p>Order Taking</p>
          </div>
        </div>
        <h2 className="auth-title">Pair this tablet</h2>
        <p className="auth-sub">
          Enter the pairing code from your manager's admin dashboard. You only do this once — the
          tablet stays paired to this branch afterwards.
        </p>
        <PairingCodeForm onSubmit={handlePair} submitting={submitting} error={error} />
      </div>
    </main>
  );
}
