/**
 * Customers → Bulk import (CSV).
 *
 * Two-step UX:
 *   1. Operator picks a CSV → we hit the backend with dry_run=true
 *      and show a preview: which rows will be created vs updated.
 *   2. They click "Confirm import" → same payload with dry_run=false.
 *
 * Per-row preview is the safety net: a wholesaler with 800 buyers
 * doesn't want to find out after the fact that a misnamed column
 * created 800 duplicates.
 */

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/feedback/Toast";
import { useAuthStore } from "@/stores/auth";

interface PreviewRow {
  row_no: number;
  name: string;
  ntn: string | null;
  phone: string | null;
  action: "create" | "update";
}

interface ImportResult {
  rows_total: number;
  rows_valid: number;
  rows_skipped: number;
  errors: string[];
  preview: PreviewRow[];
  would_create: number;
  would_update: number;
  created: number;
  updated: number;
}

const SAMPLE_CSV = [
  "name,phone,email,ntn,address,province,registration_type",
  "Sialkot Hardware (Pvt) Ltd,+92-300-1234567,acc@sialkot.example,1234567,Iqbal Town Sialkot,Punjab,registered",
  "Karachi Cold Storage,02199990000,,9876543,Korangi Industrial,Sindh,registered",
  "Walk-in B2B,03001112222,,,,KP,unregistered",
].join("\n");

async function postImport(file: File, dryRun: boolean): Promise<ImportResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("dry_run", dryRun ? "true" : "false");
  // We bypass the generic api() wrapper because FormData and JSON
  // Content-Type don't mix. Hand-roll the request with bearer.
  const access = useAuthStore.getState().access;
  const resp = await fetch("/api/customers/import/", {
    method: "POST",
    headers: access ? { Authorization: `Bearer ${access}` } : {},
    body: fd,
  });
  if (!resp.ok && resp.status !== 201) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${resp.status}`);
  }
  return resp.json();
}

export default function CustomerImportRoute() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const toast = useToast();

  async function onPickFile(f: File) {
    setFile(f);
    setBusy(true);
    setErrorMsg(null);
    setResult(null);
    try {
      const r = await postImport(f, true);
      setResult(r);
    } catch (err) {
      setErrorMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!file) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const r = await postImport(file, false);
      setResult(r);
      toast.show({
        message: `Imported. Created ${r.created}, updated ${r.updated}.`,
        variant: "success",
      });
    } catch (err) {
      setErrorMsg((err as Error).message);
      toast.show({
        message: `Import failed: ${(err as Error).message}`,
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  }

  function downloadSample() {
    const blob = new Blob([SAMPLE_CSV], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "customers-sample.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return (
    <div className="space-y-4">
      <div>
        <Link to="/customers" className="text-sm text-muted-foreground hover:underline">
          ← Customers
        </Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Import customers</h1>
        <p className="text-sm text-muted-foreground">
          Bulk-add your buyers from a CSV. Existing buyers are matched
          by NTN (or name + phone) and updated in place.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">CSV format</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <p>
            Columns (case-insensitive, order doesn't matter):
            {" "}
            <code className="rounded bg-muted px-1 text-xs">
              name, phone, email, ntn, cnic, address, province, registration_type
            </code>
          </p>
          <p className="mt-1 text-muted-foreground">
            <span className="font-medium">name</span> is the only required
            column. <span className="font-medium">registration_type</span>
            {" "}must be <span className="font-mono">registered</span> or
            {" "}<span className="font-mono">unregistered</span> — defaults
            to unregistered.
          </p>
          <Button variant="outline" size="sm" className="mt-3" onClick={downloadSample}>
            Download sample CSV
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">1. Pick your CSV</CardTitle>
        </CardHeader>
        <CardContent>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onPickFile(f);
            }}
            className="hidden"
            aria-label="Choose CSV file"
          />
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
          >
            <Upload className="mr-1 h-4 w-4" />
            {file ? `Replace file (${file.name})` : "Choose file"}
          </Button>
          {busy && (
            <p className="mt-2 text-xs text-muted-foreground">
              Parsing…
            </p>
          )}
          {errorMsg && (
            <p className="mt-2 text-xs text-destructive">{errorMsg}</p>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              <span>2. Review preview</span>
              <span className="flex gap-1.5">
                <Badge variant="info">{result.rows_total} rows</Badge>
                <Badge variant="success">{result.would_create} new</Badge>
                <Badge variant="warning">{result.would_update} updates</Badge>
                {result.rows_skipped > 0 && (
                  <Badge variant="destructive">{result.rows_skipped} skipped</Badge>
                )}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {result.errors.length > 0 && (
              <ul className="mb-3 list-disc rounded-md border border-destructive/40 bg-destructive-soft p-3 pl-6 text-xs text-destructive-soft-foreground">
                {result.errors.map((e, i) => (<li key={i}>{e}</li>))}
              </ul>
            )}
            <div className="max-h-80 overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs">
                  <tr>
                    <th className="px-2 py-1 text-left">Row</th>
                    <th className="px-2 py-1 text-left">Name</th>
                    <th className="px-2 py-1 text-left">NTN</th>
                    <th className="px-2 py-1 text-left">Phone</th>
                    <th className="px-2 py-1 text-left">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {result.preview.map((p) => (
                    <tr key={p.row_no} className="border-t">
                      <td className="px-2 py-1 font-mono text-xs">{p.row_no}</td>
                      <td className="px-2 py-1">{p.name}</td>
                      <td className="px-2 py-1 font-mono text-xs">{p.ntn ?? "—"}</td>
                      <td className="px-2 py-1 font-mono text-xs">{p.phone ?? "—"}</td>
                      <td className="px-2 py-1">
                        {p.action === "create"
                          ? <Badge variant="success">New</Badge>
                          : <Badge variant="warning">Update</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Show the commit button only when nothing has been committed yet
                (created + updated === 0 means we're still in dry-run). */}
            {result.created === 0 && result.updated === 0 ? (
              <div className="mt-4 flex items-center justify-end gap-2">
                <Button variant="outline" disabled={busy} onClick={() => {
                  setFile(null); setResult(null); setErrorMsg(null);
                }}>
                  Cancel
                </Button>
                <Button onClick={commit} disabled={busy || result.rows_valid === 0}>
                  {busy ? "Importing…" : `Confirm import of ${result.rows_valid} row(s)`}
                </Button>
              </div>
            ) : (
              <p className="mt-4 rounded-md bg-success-soft p-3 text-sm text-success-soft-foreground">
                Imported. <strong>Created {result.created}</strong> · <strong>Updated {result.updated}</strong>.
                {" "}<Link to="/customers" className="underline">Back to customers</Link>.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
