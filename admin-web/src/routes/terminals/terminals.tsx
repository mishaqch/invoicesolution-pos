import { Copy, Download, Loader2, Monitor, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/feedback/Toast";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useCreateTerminal,
  useDeactivateTerminal,
  useIssuePairingCode,
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
  const [v, setV] = useState({ branch: "", name: "" });
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
      await create.mutateAsync({ branch: v.branch, name: v.name });
      setV({ branch: v.branch, name: "" });
      toast.show({ message: "Terminal created — share the pairing code below.", variant: "success" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Terminals</h1>
        <a href={DOWNLOAD_URL} download>
          <Button variant="outline">
            <Download className="mr-2 h-4 w-4" /> Download Terminal App
          </Button>
        </a>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">How to set up a counter</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          <p>1. Click <strong>Download Terminal App</strong> and install <span className="font-mono">invoiceSolution.exe</span> on the Windows counter PC (Windows 10 or newer).</p>
          <p>2. Add a terminal below for the branch — you'll get a one-time <strong>pairing code</strong>.</p>
          <p>3. Launch the app on the counter and enter the code. It binds to that branch and is ready to ring FBR-fiscalized sales.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Add terminal</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Branch *</Label>
              <Select value={v.branch} onChange={(e) => setV({ ...v, branch: e.target.value })} required>
                <option value="">Select branch…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Name *</Label>
              <Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder="Counter 1" required />
            </div>
            <div className="col-span-2 flex items-center gap-3">
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
        <CardHeader><CardTitle>Terminals</CardTitle></CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
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
                  <TableHead>Branch</TableHead>
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
      </TableCell>
      <TableCell>{branchName}</TableCell>
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
        {t.is_paired ? (
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
          {!t.is_paired && t.is_active && (
            <Button
              variant="outline" size="sm"
              onClick={() => issue.mutate(t.id)}
              loading={issue.isPending}
              title="Generate a fresh pairing code"
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
              {t.pairing_code ? "New code" : "Issue code"}
            </Button>
          )}
          {t.is_active && (
            <Button
              variant="ghost" size="sm"
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
        </div>
      </TableCell>
    </TableRow>
  );
}
