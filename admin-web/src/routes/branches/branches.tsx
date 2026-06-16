import { CheckCircle2, Info, Loader2, Plus, Settings2, XCircle } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIsDigitalInvoicing, useIsImsSdc } from "@/features/modules/hooks";
import { useToast } from "@/components/feedback/Toast";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useCreateBranch,
  useDeactivateBranchToken,
  useFbrPosStatus,
  useSetBranchToken,
  useTestFbrToken,
  useUpdateBranch,
  type FbrPosBranch,
  type TestTokenResult,
} from "@/lib/queries";

import type { Branch } from "@pos/shared/types";

const PRAL_DEFAULT_URL = "https://gw.fbr.gov.pk";

const PROVINCES = [
  "PUNJAB", "SINDH", "KP", "BALOCHISTAN", "ICT", "GB", "AJK",
] as const;

export default function BranchesList() {
  const { data, isLoading } = useBranches();
  const { data: posStatus } = useFbrPosStatus();
  const imsSdc = useIsImsSdc();
  // Digital-Invoicing tenants submit to FBR through the central DI-API token at
  // the tenant level — there's no per-branch POS registration. So hide the
  // whole "FBR POS" column + per-branch token editor for them; a DI branch is
  // purely an organisational unit (name / code / city) that holds warehouses.
  const di = useIsDigitalInvoicing();
  const create = useCreateBranch();
  const [v, setV] = useState({
    name: "", code: "", address: "", city: "", province: "PUNJAB" as const,
  });
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const posByBranch = new Map<string, FbrPosBranch>(
    (posStatus?.branches ?? []).map((p) => [p.branch_id, p]),
  );

  // Column count for empty/loading rows. Base columns: Name, Code, City,
  // Province, Active, actions = 6. + FBR POS (non-DI). + Token (non-DI, non-IMS).
  const colCount = 6 + (di ? 0 : 1) + (!di && !imsSdc ? 1 : 0);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync(v);
      setV({ name: "", code: "", address: "", city: "", province: "PUNJAB" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  const branches = data?.results ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="Branches" />

      <Card>
        <CardHeader><CardTitle>Add branch</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name *"><Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} required /></Field>
            <Field label="Code *"><Input value={v.code} onChange={(e) => setV({ ...v, code: e.target.value })} required /></Field>
            <Field label="City *"><Input value={v.city} onChange={(e) => setV({ ...v, city: e.target.value })} required /></Field>
            <Field label="Province *">
              <Select value={v.province} onChange={(e) => setV({ ...v, province: e.target.value as typeof v.province })}>
                {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Address *">
                <Input value={v.address} onChange={(e) => setV({ ...v, address: e.target.value })} required />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" loading={create.isPending}>
                <Plus className="mr-2 h-4 w-4" /> {create.isPending ? "Adding…" : "Add"}
              </Button>
              {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="hidden lg:table-cell">Code</TableHead>
              <TableHead className="hidden md:table-cell">City</TableHead>
              <TableHead className="hidden xl:table-cell">Province</TableHead>
              {/* FBR POS registration is a POS concept — hidden for Digital
                  Invoicing (those submit via the central DI-API token). */}
              {!di && <TableHead>FBR POS</TableHead>}
              {!di && !imsSdc && <TableHead className="hidden lg:table-cell">Token</TableHead>}
              <TableHead className="hidden md:table-cell">Active</TableHead>
              <TableHead className="w-px" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={colCount} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : branches.length === 0 ? (
              <TableRow><TableCell colSpan={colCount} className="text-center text-muted-foreground">No branches yet.</TableCell></TableRow>
            ) : (
              branches.map((b) => (
                <BranchRow
                  key={b.id}
                  branch={b}
                  pos={posByBranch.get(b.id)}
                  imsSdc={imsSdc}
                  di={di}
                  colCount={colCount}
                  expanded={editing === b.id}
                  onToggle={() => setEditing(editing === b.id ? null : b.id)}
                />
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function BranchRow({
  branch,
  pos,
  imsSdc,
  di,
  colCount,
  expanded,
  onToggle,
}: {
  branch: Branch;
  pos?: FbrPosBranch;
  imsSdc: boolean;
  di: boolean;
  colCount: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const registered = !!branch.fbr_pos_id;
  const hasToken = !!pos?.has_branch_token;
  const tokenActive = !!pos?.branch_token_active;
  return (
    <>
      <TableRow>
        <TableCell>
          {branch.name}
          <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">{branch.code}</span>
        </TableCell>
        <TableCell className="hidden font-mono text-xs lg:table-cell">{branch.code}</TableCell>
        <TableCell className="hidden md:table-cell">{branch.city}</TableCell>
        <TableCell className="hidden xl:table-cell">{branch.province}</TableCell>
        {!di && (
          <TableCell>
            {registered ? (
              <Badge variant="success" className="gap-1">
                <CheckCircle2 className="h-3 w-3" /> POS {branch.fbr_pos_id}
              </Badge>
            ) : (
              <Badge variant="muted">Not registered</Badge>
            )}
          </TableCell>
        )}
        {!di && !imsSdc && (
          <TableCell className="hidden lg:table-cell">
            {!hasToken ? (
              <Badge variant="muted">No token</Badge>
            ) : tokenActive ? (
              <Badge variant="success">Token set</Badge>
            ) : (
              <Badge variant="warning">Inactive</Badge>
            )}
          </TableCell>
        )}
        <TableCell className="hidden md:table-cell">{branch.is_active ? "Yes" : "No"}</TableCell>
        <TableCell>
          {/* DI branches have no per-branch FBR POS registration to edit. */}
          {!di && (
            <Button variant="ghost" size="sm" onClick={onToggle}>
              <Settings2 className="mr-1 h-4 w-4" /> FBR POS
            </Button>
          )}
        </TableCell>
      </TableRow>
      {!di && expanded && (
        <TableRow>
          <TableCell colSpan={colCount} className="bg-muted/30">
            <FbrPosEditor branch={branch} pos={pos} onDone={onToggle} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/**
 * Per-branch FBR POS registration editor.
 *
 * The POS ID + Code are issued by FBR when the outlet is registered as a POS
 * under Digital Invoicing. We store them for traceability and to print on
 * receipts — they are NOT sent in the PRAL invoice payload. What actually
 * connects this outlet to FBR is the production security Token (entered on
 * the FBR / PRAL setup page); submitting an invoice with that token flips the
 * POS from "Disconnected" to "Connected" on the FBR portal.
 */
function FbrPosEditor({
  branch,
  pos,
  onDone,
}: {
  branch: Branch;
  pos?: FbrPosBranch;
  onDone: () => void;
}) {
  const update = useUpdateBranch();
  const setToken = useSetBranchToken();
  const deactivate = useDeactivateBranchToken();
  const test = useTestFbrToken();
  const toast = useToast();
  const imsSdc = useIsImsSdc();

  const [posId, setPosId] = useState(branch.fbr_pos_id ?? "");
  const [posCode, setPosCode] = useState(branch.fbr_pos_code ?? "");
  const [token, setTokenValue] = useState("");
  const [endpoint, setEndpoint] = useState(PRAL_DEFAULT_URL);
  const [testResult, setTestResult] = useState<TestTokenResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasToken = !!pos?.has_branch_token;
  const tokenActive = !!pos?.branch_token_active;

  const idDirty =
    posId.trim() !== (branch.fbr_pos_id ?? "") ||
    posCode.trim() !== (branch.fbr_pos_code ?? "");

  async function saveIds() {
    setError(null);
    try {
      await update.mutateAsync({
        id: branch.id,
        fbr_pos_id: posId.trim() || null,
        fbr_pos_code: posCode.trim() || null,
      });
      toast.show({ message: `Saved POS ID/Code for ${branch.name}.`, variant: "success" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  async function onTest() {
    setError(null);
    setTestResult(null);
    try {
      setTestResult(await test.mutateAsync({ token, api_endpoint: endpoint }));
    } catch (err) {
      setTestResult({ ok: false, detail: extractApiErrorMessage(err) });
    }
  }

  async function saveToken() {
    setError(null);
    try {
      await setToken.mutateAsync({
        branch_id: branch.id, token, api_endpoint: endpoint,
      });
      setTokenValue("");
      setTestResult(null);
      toast.show({ message: `POS token saved for ${branch.name}.`, variant: "success" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  async function onDeactivate() {
    setError(null);
    try {
      await deactivate.mutateAsync(branch.id);
      toast.show({ message: `POS token deactivated for ${branch.name}.`, variant: "info" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  // IMS / SDC tenants: the FBR Fiscalization service on the shop machine holds
  // the token and does the activation handshake. Our platform only needs this
  // branch's FBR POS ID (we send it to the local SDC). No POS Code (never sent)
  // and no Bearer token (the SDC path uses none) — so show a minimal editor.
  if (imsSdc) {
    return (
      <div className="space-y-5 py-2">
        <div className="flex items-start gap-2 rounded-md border border-info-soft bg-info-soft/40 p-3 text-sm text-info-soft-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">FBR POS ID for this outlet</p>
            <p className="text-muted-foreground">
              This outlet fiscalizes through the FBR Fiscalization (IMS) service
              running on its counter PC. Enter the branch's{" "}
              <strong>FBR POS ID</strong> (from the FBR portal) — that's all the
              platform needs; the IMS service handles the token and activation.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <div className="grid max-w-xs gap-3">
            <Field label="FBR POS ID">
              <Input value={posId} onChange={(e) => setPosId(e.target.value)}
                placeholder="e.g. 194444" inputMode="numeric" />
            </Field>
          </div>
          <Button
            size="sm"
            onClick={saveIds}
            loading={update.isPending}
            disabled={posId.trim() === (branch.fbr_pos_id ?? "")}
          >
            Save POS ID
          </Button>
          {pos?.connected && (
            <p className="flex items-center gap-1.5 text-sm text-success-soft-foreground">
              <CheckCircle2 className="h-4 w-4" /> Connected — last fiscalized{" "}
              {pos.last_validated_at ? new Date(pos.last_validated_at).toLocaleString() : ""}
            </p>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div><Button variant="outline" size="sm" onClick={onDone}>Close</Button></div>
      </div>
    );
  }

  return (
    <div className="space-y-5 py-2">
      <div className="flex items-start gap-2 rounded-md border border-info-soft bg-info-soft/40 p-3 text-sm text-info-soft-foreground">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          <p className="font-medium">FBR POS registration for this outlet</p>
          <p className="text-muted-foreground">
            Each outlet is its own registered POS with its own FBR credentials.
            Enter this branch's <strong>POS ID</strong>, <strong>Code</strong>{" "}
            and <strong>security token</strong> from the FBR portal. The token
            authenticates this branch's invoices; the POS ID/Code are stored for
            your records and receipts. Once a sale from this outlet is submitted
            with the token, the FBR portal shows the POS as{" "}
            <strong>Connected</strong>.
          </p>
        </div>
      </div>

      {/* POS ID + Code */}
      <div className="space-y-2">
        <div className="grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="FBR POS ID">
            <Input value={posId} onChange={(e) => setPosId(e.target.value)}
              placeholder="e.g. 194444" inputMode="numeric" />
          </Field>
          <Field label="FBR POS Code">
            <Input value={posCode} onChange={(e) => setPosCode(e.target.value)}
              placeholder="e.g. 3364862B" />
          </Field>
        </div>
        <Button size="sm" onClick={saveIds} disabled={!idDirty || update.isPending}>
          {update.isPending ? "Saving…" : "Save POS ID / Code"}
        </Button>
      </div>

      {/* Branch token */}
      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Branch security token</span>
          {!hasToken ? (
            <Badge variant="muted">No token</Badge>
          ) : tokenActive ? (
            <Badge variant="success">Token on file</Badge>
          ) : (
            <Badge variant="warning">Inactive</Badge>
          )}
        </div>
        <div className="grid max-w-xl gap-3">
          <Field label="API endpoint">
            <Input value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
              placeholder={PRAL_DEFAULT_URL} />
          </Field>
          <Field label="Bearer token">
            <Input type="password" value={token} autoComplete="off"
              onChange={(e) => setTokenValue(e.target.value)}
              placeholder={hasToken
                ? "Token on file — paste a new one to replace"
                : "paste this branch's FBR token"} />
          </Field>
        </div>

        {test.isPending && (
          <p className="flex items-center gap-2 text-sm text-info-soft-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Asking PRAL to validate the token…
          </p>
        )}
        {testResult && !test.isPending && (
          testResult.ok ? (
            <p className="flex items-center gap-2 text-sm text-success-soft-foreground">
              <CheckCircle2 className="h-4 w-4" /> Connection OK — PRAL accepted the token
              {typeof testResult.uom_count === "number" ? ` (${testResult.uom_count} UoMs).` : "."}
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-destructive">
              <XCircle className="h-4 w-4" /> {testResult.detail}
            </p>
          )
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={onTest}
            disabled={!token || !endpoint || test.isPending}>
            {test.isPending ? "Testing…" : "Test connection"}
          </Button>
          <Button size="sm" onClick={saveToken}
            disabled={(!token && !hasToken) || setToken.isPending}>
            {setToken.isPending ? "Saving…" : hasToken && !token ? "Save (keep token)" : "Save token"}
          </Button>
          {hasToken && tokenActive && (
            <Button variant="ghost" size="sm" onClick={onDeactivate} loading={deactivate.isPending}>
              {deactivate.isPending ? "Deactivating…" : "Deactivate token"}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          POS registrations get a production token directly from FBR — no
          sandbox or scenario testing. The token is stored encrypted and never
          shown again. <strong>Test connection</strong> probes PRAL read-only
          (no invoice is sent); it must run from a PRAL-whitelisted server IP.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div>
        <Button variant="outline" size="sm" onClick={onDone}>Close</Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
