import { Copy, Download, Loader2, Monitor, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/feedback/Toast";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useCreateTerminal,
  useDeactivateTerminal,
  useIssuePairingCode,
  useReactivateTerminal,
  useRenameTerminal,
  useTerminals,
  type AdminTerminal,
} from "@/lib/queries";

// The installer is served at the site root (nginx → media/downloads), same
// origin as admin-web, so a relative link works in dev (Vite proxy) + prod.
const DOWNLOAD_URL = "/download/terminal/";

export default function TerminalsList() {
  const { data: branchData } = useBranches();
  const { data, isLoading } = useTerminals();
  const create = useCreateTerminal();
  const toast = useToast();

  const branches = branchData?.results ?? [];
  const [v, setV] = useState({ branch: "", name: "", is_order_taking_only: false });
  const [error, setError] = useState<string | null>(null);

  const terminals = data?.results ?? [];
  const branchName = (id: string) => branches.find((b) => b.id === id)?.name ?? "—";

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!v.branch) {
      setError("Choose a branch.");
      return;
    }
    try {
      await create.mutateAsync({
        branch: v.branch,
        name: v.name,
        is_order_taking_only: v.is_order_taking_only,
      });
      setV({ branch: v.branch, name: "", is_order_taking_only: false });
      toast.show({
        message: "Terminal created — share the pairing code below.",
        variant: "success",
      });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Terminals"
        actions={
          <a href={DOWNLOAD_URL} download>
            <Button variant="outline">
              <Download className="mr-2 h-4 w-4" /> Download Terminal App
            </Button>
          </a>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">How to set up a counter</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          <p>
            1. Click <strong>Download Terminal App</strong> and install{" "}
            <span className="font-mono">invoiceSolution.exe</span> on the Windows counter PC
            (Windows 10 or newer).
          </p>
          <p>
            2. Add a terminal below for the branch — you'll get a one-time{" "}
            <strong>pairing code</strong>.
          </p>
          <p>
            3. Launch the app on the counter and enter the code. It binds to that branch and is
            ready to ring FBR-fiscalized sales.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add terminal</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Branch *</Label>
              <Select
                value={v.branch}
                onChange={(e) => setV({ ...v, branch: e.target.value })}
                required
              >
                <option value="">Select branch…</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Name *</Label>
              <Input
                value={v.name}
                onChange={(e) => setV({ ...v, name: e.target.value })}
                placeholder="Counter 1"
                required
              />
            </div>
            <label className="flex items-start gap-2 sm:col-span-2 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4"
                checked={v.is_order_taking_only}
                onChange={(e) => setV({ ...v, is_order_taking_only: e.target.checked })}
              />
              <span className="text-sm">
                <span className="font-medium">Waiter tablet (order-taking only)</span>
                <span className="block text-muted-foreground">
                  A shared tablet waiters use to take restaurant orders. It fires orders to the
                  kitchen but never charges — a cashier till closes the bill. Pair it in the browser
                  (waiter app), not the .exe.
                </span>
              </span>
            </label>
            <div className="flex items-center gap-3 sm:col-span-2">
              <Button type="submit" loading={create.isPending}>
                {!create.isPending && <Plus className="mr-2 h-4 w-4" />}
                Add terminal
              </Button>
              {error && <span className="text-sm text-destructive">{error}</span>}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Terminals</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : terminals.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
              <Monitor className="h-8 w-8" />
              <p>No terminals yet. Add one above to get a pairing code.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead className="hidden md:table-cell">Branch</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Pairing code</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {terminals.map((tm) => (
                  <TerminalRow key={tm.id} t={tm} branchName={branchName(tm.branch)} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TerminalRow({ t, branchName }: { t: AdminTerminal; branchName: string }) {
  const issue = useIssuePairingCode();
  const deactivate = useDeactivateTerminal();
  const reactivate = useReactivateTerminal();
  const rename = useRenameTerminal();
  const toast = useToast();

  const copy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      toast.show({ message: "Pairing code copied.", variant: "success" });
    } catch {
      toast.show({ message: "Copy failed — select it manually.", variant: "warning" });
    }
  };

  return (
    <TableRow>
      <TableCell className="font-medium">
        {t.name}
        {t.terminal_index != null && (
          <span className="ml-1 text-xs text-muted-foreground">· T{t.terminal_index}</span>
        )}
        {t.is_order_taking_only && (
          <Badge variant="outline" className="ml-2 text-[10px] font-normal">
            Waiter tablet
          </Badge>
        )}
        <span className="block text-[11px] text-muted-foreground md:hidden">{branchName}</span>
      </TableCell>
      <TableCell className="hidden md:table-cell">{branchName}</TableCell>
      <TableCell>
        {!t.is_active ? (
          <Badge variant="secondary">Deactivated</Badge>
        ) : t.is_paired ? (
          <Badge className="bg-green-600 hover:bg-green-600">Paired</Badge>
        ) : (
          <Badge variant="outline">Awaiting pairing</Badge>
        )}
      </TableCell>
      <TableCell>
        {/* A LIVE code wins over the paired badge: after a Re-pair the owner
            must be able to read the new code, and the terminal still shows as
            paired until the till redeems it. */}
        {t.is_paired && !t.pairing_code ? (
          <span className="text-xs text-muted-foreground">
            Paired {t.paired_at ? new Date(t.paired_at).toLocaleDateString() : ""}
          </span>
        ) : t.pairing_code ? (
          <button
            onClick={() => copy(t.pairing_code!)}
            className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 font-mono text-sm hover:bg-muted"
            title="Click to copy"
          >
            {t.pairing_code}
            <Copy className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        ) : (
          <span className="text-xs text-muted-foreground">— issue a code →</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-2">
          {t.is_active && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                // Re-pairing an ALREADY-paired terminal is the recovery path
                // when a till loses its local pairing (pos.sqlite replaced or
                // reset) and asks for a code again while admin still shows it
                // paired. The server redeems onto the SAME terminal row — the
                // terminal keeps its index and every invoice attached to it —
                // so this must never require deleting and re-creating the
                // terminal, which would renumber it (KK-T2 -> KK-T5).
                if (
                  t.is_paired &&
                  !window.confirm(
                    `${t.name} is already paired.\n\n` +
                      "Issue a new code only if this till has lost its pairing " +
                      "and is asking for a code again. The terminal keeps its " +
                      "number and all its invoices.\n\nIssue a new code?",
                  )
                ) {
                  return;
                }
                issue.mutate(t.id);
              }}
              loading={issue.isPending}
              title={
                t.is_paired
                  ? "Re-pair this terminal (e.g. after a reinstall)"
                  : "Generate a fresh pairing code"
              }
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
              {t.is_paired ? "Re-pair" : t.pairing_code ? "New code" : "Issue code"}
            </Button>
          )}
          {t.is_active && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (window.confirm(`Deactivate ${t.name}? It will stop being usable for sales.`)) {
                  deactivate.mutate(t.id);
                }
              }}
              loading={deactivate.isPending}
              title="Deactivate terminal"
            >
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          )}
          {/* A deactivated terminal used to render with NO actions at all —
              a dead row the owner could neither revive, rename nor remove.
              Deactivation is a soft delete (the row must outlive its invoices),
              so Reactivate is the way back. */}
          {!t.is_active && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (
                  window.confirm(
                    `Bring ${t.name} back into service?\n\n` +
                      "It keeps its terminal number" +
                      (t.terminal_index ? ` (T${t.terminal_index})` : "") +
                      " and any history. You can then issue a pairing code for it.",
                  )
                ) {
                  reactivate.mutate(t.id);
                }
              }}
              loading={reactivate.isPending}
              title="Bring this terminal back into service"
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
              Reactivate
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              const next = window.prompt(`Rename terminal`, t.name);
              if (next && next.trim() && next.trim() !== t.name) {
                rename.mutate({ id: t.id, name: next.trim() });
              }
            }}
            loading={rename.isPending}
            title="Rename terminal"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
