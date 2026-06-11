import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { useAudits, useBranches } from "@/lib/queries";

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  open: "outline",
  in_progress: "default",
  finalized: "secondary",
  cancelled: "destructive",
};

export default function StockAuditsList() {
  const { data, isLoading } = useAudits();
  const branches = useBranches();
  const branchName = (id: string) =>
    branches.data?.results?.find((b) => b.id === id)?.name ?? id;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stock audits"
        subtitle="Physical counts compared against system stock. Finalizing an audit generates adjustments for any variance."
      />

      <Card>
        <CardContent className="overflow-x-auto p-0">
          {isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Loading…</p>
          ) : !data || data.results.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No audits yet. Start one from a branch's stock view.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Audit #</th>
                  <th className="hidden px-3 py-2 text-left font-medium md:table-cell">Branch</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Items</th>
                  <th className="hidden px-3 py-2 text-left font-medium lg:table-cell">Started</th>
                  <th className="hidden px-3 py-2 text-left font-medium lg:table-cell">Finalized</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((a) => (
                  <tr key={a.id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link to={`/inventory/audits/${a.id}`} className="hover:underline">
                        {a.audit_number}
                      </Link>
                      <span className="block text-[11px] text-muted-foreground md:hidden">
                        {branchName(a.branch)}
                      </span>
                    </td>
                    <td className="hidden px-3 py-2 md:table-cell">{branchName(a.branch)}</td>
                    <td className="px-3 py-2">
                      <Badge variant={STATUS_VARIANTS[a.status] ?? "outline"}>
                        {a.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right">{a.items?.length ?? 0}</td>
                    <td className="hidden px-3 py-2 text-xs text-muted-foreground lg:table-cell">
                      {a.started_at ? new Date(a.started_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="hidden px-3 py-2 text-xs text-muted-foreground lg:table-cell">
                      {a.finalized_at ? new Date(a.finalized_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
