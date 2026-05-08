import { ArrowLeft, CheckCircle2, FileWarning, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/stores/auth";

interface DryRunResult {
  counts: { new: number; updated: number; errored: number; total_rows: number };
  errors: { row: number; column: string; message: string }[];
}

interface CommitResult {
  created: number;
  updated: number;
}

const API_BASE = "/api";

export default function CsvImport() {
  const navigate = useNavigate();
  const access = useAuthStore((s) => s.access);

  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function postFile(target: "dry-run" | "commit"): Promise<DryRunResult | CommitResult> {
    if (!file) throw new Error("Pick a file first.");
    const formData = new FormData();
    formData.append("file", file);
    const url =
      `${API_BASE}/catalog/products/import/` +
      (target === "dry-run" ? "?dry_run=true" : "");
    const resp = await fetch(url, {
      method: "POST",
      body: formData,
      headers: { Authorization: `Bearer ${access}` },
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(text || `Server returned ${resp.status}`);
    }
    return resp.json();
  }

  async function onDryRun() {
    setError(null);
    setBusy(true);
    setDryRun(null);
    try {
      const result = (await postFile("dry-run")) as DryRunResult;
      setDryRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dry-run failed");
    } finally {
      setBusy(false);
    }
  }

  async function onCommit() {
    setError(null);
    setBusy(true);
    try {
      const result = (await postFile("commit")) as CommitResult;
      alert(`Imported: ${result.created} created, ${result.updated} updated.`);
      navigate("/catalog/products");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Commit failed");
    } finally {
      setBusy(false);
    }
  }

  const canCommit = dryRun !== null && dryRun.counts.errored === 0 && (dryRun.counts.new + dryRun.counts.updated) > 0;

  return (
    <div className="space-y-4">
      <Link to="/catalog/products" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to products
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">Import products from CSV</h1>

      <Card>
        <CardHeader>
          <CardTitle>1. Pick a CSV file</CardTitle>
          <CardDescription>
            Required columns: <code>sku</code>, <code>name</code>, <code>uom_code</code>, <code>sale_price</code>.
            Optional: barcode, name_ur, description, category, hs_code, tax_rate, cost_price,
            retail_price, min_sale_price, max_discount_pct, reorder_level, is_active, is_taxable.
            UTF-8 with or without BOM.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setDryRun(null);
              setError(null);
            }}
          />
          {file && <p className="text-sm text-muted-foreground">Selected: <strong>{file.name}</strong></p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Validate (dry-run)</CardTitle>
          <CardDescription>Verifies every row without writing anything.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button onClick={onDryRun} disabled={!file || busy}>
            <Upload className="mr-2 h-4 w-4" />
            {busy ? "Validating…" : "Run dry-run"}
          </Button>

          {dryRun && (
            <div className="rounded-md border bg-muted/30 p-4">
              <div className="flex items-center gap-3 text-sm">
                {dryRun.counts.errored === 0 ? (
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                ) : (
                  <FileWarning className="h-5 w-5 text-destructive" />
                )}
                <span>
                  {dryRun.counts.new} new • {dryRun.counts.updated} updated •{" "}
                  <span className={dryRun.counts.errored > 0 ? "text-destructive font-medium" : ""}>
                    {dryRun.counts.errored} errored
                  </span>{" "}
                  / {dryRun.counts.total_rows} total
                </span>
              </div>

              {dryRun.errors.length > 0 && (
                <div className="mt-3 max-h-64 overflow-auto rounded-md border bg-background p-3 text-xs font-mono">
                  {dryRun.errors.slice(0, 100).map((err, i) => (
                    <div key={i}>row {err.row}: <strong>{err.column}</strong> — {err.message}</div>
                  ))}
                  {dryRun.errors.length > 100 && (
                    <div className="mt-1 text-muted-foreground">
                      … {dryRun.errors.length - 100} more error(s)
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Commit</CardTitle>
          <CardDescription>Enabled when the dry-run reports no errors.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={onCommit} disabled={!canCommit || busy}>
            {busy ? "Importing…" : "Import products"}
          </Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
