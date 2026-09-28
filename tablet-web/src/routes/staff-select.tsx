import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchRoster } from "@/api/terminals";
import { extractApiErrorMessage } from "@/lib/api";
import { StaffTile } from "@/components/auth/StaffTile";
import { useDeviceStore } from "@/stores/device";
import type { RosterResponse, RosterStaff } from "@/types";

/** /staff — roster tiles. Tap a name -> PIN screen. */
export default function StaffSelectRoute() {
  const navigate = useNavigate();
  const terminalId = useDeviceStore((s) => s.terminalId);
  const deviceFingerprint = useDeviceStore((s) => s.deviceFingerprint);
  const branchName = useDeviceStore((s) => s.branchName);
  const unpair = useDeviceStore((s) => s.unpair);

  const rosterQuery = useQuery<RosterResponse>({
    queryKey: ["roster", terminalId],
    queryFn: () =>
      fetchRoster({ terminal_id: terminalId as string, device_fingerprint: deviceFingerprint }),
    enabled: !!terminalId,
  });

  function selectStaff(staff: RosterStaff) {
    navigate(`/pin?email=${encodeURIComponent(staff.email)}&name=${encodeURIComponent(staff.name)}`);
  }

  return (
    <main className="auth-wrap">
      <div className="auth-card">
        <div className="auth-brand">
          <img src="/logo-tdcp.png" alt="TDCP Lake Resort" width={52} height={50} />
          <div>
            <h1>{branchName || "TDCP Lake Resort"}</h1>
            <p>Order Taking</p>
          </div>
        </div>
        <h2 className="auth-title">Who's serving?</h2>
        <p className="auth-sub">Tap your name to sign in with your 6-digit PIN.</p>

        {rosterQuery.isLoading ? (
          <div style={{ display: "grid", placeItems: "center", padding: "30px" }}>
            <div className="page-spin" role="status" aria-label="Loading staff" />
          </div>
        ) : rosterQuery.isError ? (
          <div className="auth-err" role="alert">
            {extractApiErrorMessage(rosterQuery.error)}
          </div>
        ) : (
          <div className="roster-grid">
            {(rosterQuery.data?.staff ?? []).map((staff) => (
              <StaffTile key={staff.email} staff={staff} onSelect={selectStaff} />
            ))}
          </div>
        )}

        <button
          className="auth-back"
          type="button"
          style={{ marginTop: 18, marginBottom: 0 }}
          onClick={() => {
            unpair();
            navigate("/pairing", { replace: true });
          }}
        >
          Un-pair this tablet
        </button>
      </div>
    </main>
  );
}
