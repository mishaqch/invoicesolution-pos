/**
 * Hook that resolves the POS terminal's runtime context after login:
 *   - the branch this terminal belongs to
 *   - the terminal row itself (for the local_invoice_number prefix)
 *   - the open cash session (if any)
 *
 * Phase 2 simplification: the POS picks the first branch + terminal returned
 * by the API. Phase 8 will wire a per-machine fingerprint that maps to a
 * specific terminal row.
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useSessionStore } from "@/stores/session";

import type { PosCashSessionRow } from "../../../electron/preload";

interface BranchLite {
  id: string;
  name: string;
  code: string;
}

interface TerminalLite {
  id: string;
  branch: string;
  name: string;
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
        const branches = await api<{ results: BranchLite[] }>("/branches/");
        const b = branches.results[0];
        if (!b) {
          setError("No branches configured for this tenant. Add one in admin web.");
          return;
        }
        const terminals = await api<{ results: TerminalLite[] }>(
          `/terminals/?branch=${b.id}`,
        );
        const t = terminals.results.find((x) => x.branch === b.id) ?? terminals.results[0];
        if (!t) {
          setError("No terminals configured. Add one in admin web.");
          return;
        }
        if (cancelled) return;
        setBranch(b);
        setTerminal(t);
        await loadSession(t.id);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? `API ${err.status}` : "Failed to load context.");
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
