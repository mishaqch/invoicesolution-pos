/**
 * Hook that resolves the POS terminal's runtime context after login:
 *   - the branch this terminal belongs to
 *   - the terminal row itself (for the local_invoice_number prefix)
 *   - the open cash session (if any)
 *
 * The branch + terminal come from the DEVICE PAIRING (kv_meta), not from
 * "pick the first branch the API returns". Pairing binds this physical machine
 * to exactly one terminal row in one branch, so invoice numbers can never
 * collide between terminals and every sale carries the correct branch/terminal.
 */

import { useEffect, useState } from "react";

import { useSessionStore } from "@/stores/session";

import type { PosCashSessionRow } from "../../../electron/preload";

interface BranchLite {
  id: string;
  name: string;
  code: string;
  fbrPosId: string | null;
}

interface TerminalLite {
  id: string;
  branch: string;
  name: string;
  index: number;
}

interface PosContext {
  branch: BranchLite | null;
  terminal: TerminalLite | null;
  session: PosCashSessionRow | null;
  loading: boolean;
  error: string | null;
  refreshSession: () => Promise<void>;
}

export function usePosContext(): PosContext {
  const access = useSessionStore((s) => s.access);
  const [branch, setBranch] = useState<BranchLite | null>(null);
  const [terminal, setTerminal] = useState<TerminalLite | null>(null);
  const [session, setSession] = useState<PosCashSessionRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSession = async (terminalId: string) => {
    const s = await window.api.session.current(terminalId);
    setSession(s);
  };

  useEffect(() => {
    if (!access) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const { paired, identity } = await window.api.pairing.status();
        if (!paired || !identity) {
          setError("This terminal isn't paired to a branch. Pair it first.");
          return;
        }
        if (cancelled) return;
        setBranch({
          id: identity.branchId,
          name: identity.branchName,
          code: identity.branchCode,
          fbrPosId: identity.branchFbrPosId,
        });
        setTerminal({
          id: identity.terminalId,
          branch: identity.branchId,
          name: identity.terminalName,
          index: identity.terminalIndex,
        });
        await loadSession(identity.terminalId);
      } catch {
        if (cancelled) return;
        setError("Failed to load terminal context.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [access]);

  return {
    branch, terminal, session, loading, error,
    refreshSession: async () => {
      if (terminal) await loadSession(terminal.id);
    },
  };
}
