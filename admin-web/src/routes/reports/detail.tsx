import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Download, FileSpreadsheet, FileText, Printer, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { useAuthStore } from "@/stores/auth";
import {
  useBranches,
  useReportPreview,
  useReportRegistry,
  useSaveFavorite,
} from "@/lib/queries";

function formatCell(value: unknown, kind: string): string {
  if (value === null || value === undefined || value === "") return "";
  if (kind === "money") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return `Rs. ${n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (kind === "percent") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return `${n.toFixed(2)}%`;
  }
  if (kind === "date" || kind === "datetime") {
    return String(value).slice(0, kind === "date" ? 10 : 16).replace("T", " ");
  }
  return String(value);
}

export default function ReportDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const { data: registry } = useReportRegistry();
  const meta = registry?.results.find((r) => r.name === name);

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [branchId, setBranchId] = useState("");
  const [favLabel, setFavLabel] = useState("");

  const preview = useReportPreview();
  const saveFavorite = useSaveFavorite();
  const { data: branchesPage } = useBranches();
  const branches = branchesPage?.results ?? [];

  function buildFilters(): Record<string, unknown> {
    const filters: Record<string, unknown> = {};
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    if (branchId) filters.branch_id = branchId;
    return filters;
  }

  function run() {
    preview.mutate({ name, filters: buildFilters() });
  }

  useEffect(() => {
    // Auto-run on first mount so the page isn't empty.
    preview.mutate({ name, filters: buildFilters() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name]);

  async function exportFile(format: "csv" | "xlsx" | "pdf") {
    const access = useAuthStore.getState().access;
    const resp = await fetch(`/api/reports/${name}/export/?format=${format}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: JSON.stringify(buildFilters()),
    });
    if (!resp.ok) {
      window.alert(`Export failed: ${resp.status}`);
      return;
    }
    if (resp.status === 202) {
      window.alert("Report is large — queued as a background job. Check back in a few minutes.");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function saveFav() {
    if (!favLabel.trim()) return;
    await saveFavorite.mutateAsync({
      report_name: name, label: favLabel.trim(), filters_json: buildFilters(),
    });
    setFavLabel("");
  }

  const result = preview.data;

  const tenantName = useAuthStore((s) => s.tenant?.business_name) ?? "";
  const filterSummary = [
    dateFrom || dateTo ? `Period: ${dateFrom || "…"} to ${dateTo || "…"}` : "Period: all time",
    branchId ? `Branch: ${branches.find((b) => b.id === branchId)?.name ?? branchId}` : "All branches",
  ].join("   ·   ");

  return (
    <div className="space-y-4" data-report-print>
      {/* Print-only header (the app chrome is hidden by @media print). */}
      <div className="hidden print:block">
        <div className="text-lg font-bold">{tenantName}</div>
        <div className="text-base">{name.replace(/_/g, " ")}</div>
        <div className="text-xs">{filterSummary}</div>
      </div>
      <div data-report-noprint>
      <PageHeader
        title={
          <div>
            <Link to="/reports" className="text-sm text-muted-foreground hover:underline">
              ← Reports
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight">
              {name.replace(/_/g, " ")}
            </h1>
          </div>
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer className="mr-1 h-4 w-4" /> Print
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportFile("csv")}>
              <Download className="mr-1 h-4 w-4" /> CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportFile("xlsx")}>
              <FileSpreadsheet className="mr-1 h-4 w-4" /> Excel
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportFile("pdf")}>
              <FileText className="mr-1 h-4 w-4" /> PDF
            </Button>
          </>
        }
      />
      </div>

      <Card data-report-noprint>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div>
            <Label>From</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <Label>To</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <Label>Branch</Label>
            <Select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
              <option value="">All branches</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </Select>
          </div>
          <div className="flex items-end">
            <Button size="sm" onClick={run} loading={preview.isPending}>
              {preview.isPending ? "Running…" : "Run"}
            </Button>
          </div>
          <div className="flex items-end gap-2">
            <Input value={favLabel} onChange={(e) => setFavLabel(e.target.value)} placeholder="Favorite name" />
            <Button size="sm" variant="outline" onClick={saveFav}>
              <Save className="mr-1 h-4 w-4" /> Save
            </Button>
          </div>
        </CardContent>
      </Card>

      {meta && meta.filter_fields.some((f) => !["branch_id", "date_from", "date_to"].includes(f)) && (
        <p className="text-xs text-muted-foreground">
          This report supports additional filters: {meta.filter_fields.filter((f) => !["branch_id", "date_from", "date_to"].includes(f)).join(", ")}.
        </p>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            Results
            {result && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {result.row_count} rows{result.truncated ? " (truncated)" : ""}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {!result ? (
            <p className="p-4 text-sm text-muted-foreground">No data yet.</p>
          ) : result.rows.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No rows for these filters.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  {result.columns.map((c) => (
                    <th key={c.key} className={`px-3 py-2 text-${c.align ?? "left"} font-medium`}>
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, idx) => (
                  <tr key={idx} className="border-b hover:bg-muted/30">
                    {result.columns.map((c) => (
                      <td key={c.key} className={`px-3 py-2 text-${c.align ?? "left"}`}>
                        {formatCell(row[c.key], c.kind)}
                      </td>
                    ))}
                  </tr>
                ))}
                {Object.keys(result.totals).length > 0 && (
                  <tr className="border-t bg-muted/40 font-medium">
                    {result.columns.map((c) => (
                      <td key={c.key} className={`px-3 py-2 text-${c.align ?? "left"}`}>
                        {c.key in result.totals ? formatCell(result.totals[c.key], c.kind) : ""}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
