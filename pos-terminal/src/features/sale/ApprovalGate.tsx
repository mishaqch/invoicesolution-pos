import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import { useSessionStore } from "@/stores/session";
import { SupervisorApproval, type ApprovalRequest } from "./SupervisorApproval";

type GateInput = Omit<ApprovalRequest, "onApproved">;

interface ApprovalGateCtx {
  /**
   * Run `action` only after a manager/owner authorizes it. If the current user
   * is already a supervisor (owner/manager), it runs immediately (no prompt) —
   * a manager operating the till doesn't ask themselves. Otherwise the
   * server-verified approval modal opens; `action` runs on success.
   */
  requireApproval: (req: GateInput, action: () => void) => void;
}

const Ctx = createContext<ApprovalGateCtx | null>(null);

export function ApprovalProvider({ children }: { children: ReactNode }) {
  const role = useSessionStore((s) => s.role);
  const [pending, setPending] = useState<ApprovalRequest | null>(null);

  const requireApproval = useCallback(
    (req: GateInput, action: () => void) => {
      // A supervisor running the till authorizes their own actions.
      if (role === "owner" || role === "manager") {
        action();
        return;
      }
      setPending({ ...req, onApproved: () => action() });
    },
    [role],
  );

  return (
    <Ctx.Provider value={{ requireApproval }}>
      {children}
      {pending && (
        <SupervisorApproval request={pending} onClose={() => setPending(null)} />
      )}
    </Ctx.Provider>
  );
}

export function useApprovalGate(): ApprovalGateCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApprovalGate must be used within <ApprovalProvider>");
  return ctx;
}
