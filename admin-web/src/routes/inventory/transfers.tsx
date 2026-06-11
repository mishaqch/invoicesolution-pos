import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { useBranches, useTransfers } from "@/lib/queries";

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  pending: "outline",
  in_transit: "default",
  received: "secondary",
  cancelled: "destructive",
};

export default function StockTransfersList() {
  const { data, isLoading } = useTransfers();
  const branches = useBranches();
  const branchName = (id: string) =>
    branches.data?.results?.find((b) => b.id === id)?.name ?? id;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stock transfers"
        subtitle="Move inventory between branches. Initiate at the source, receive at the destination with variance reconciliation."
      />

      <Card>
        <CardContent className="overflow-x-auto p-0">
          {isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Loading…</p>
          ) : !data || data.results.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No transfers yet. Initiate a transfer from a branch's stock view.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Transfer #</th>
                  <th className="hidden px-3 py-2 text-left font-medium md:table-cell">From</th>
                  <th className="hidden px-3 py-2 text-left font-medium md:table-cell">To</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Items</th>
                  <th className="hidden px-3 py-2 text-left font-medium lg:table-cell">Dispatched</th>
                  <th className="hidden px-3 py-2 text-left font-medium lg:table-cell">Received</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((t) => (
                  <tr key={t.id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link to={`/inventory/transfers/${t.id}`} className="hover:underline">
                        {t.transfer_number}
                      </Link>
                      <span className="block text-[11px] text-muted-foreground md:hidden">
                        {branchName(t.from_branch)} → {branchName(t.to_branch)}
                      </span>
                    </td>
                    <td className="hidden px-3 py-2 md:table-cell">{branchName(t.from_branch)}</td>
                    <td className="hidden px-3 py-2 md:table-cell">{branchName(t.to_branch)}</td>
                    <td className="px-3 py-2">
                      <Badge variant={STATUS_VARIANTS[t.status] ?? "outline"}>
                        {t.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right">{t.items?.length ?? 0}</td>
                    <td className="hidden px-3 py-2 text-xs text-muted-foreground lg:table-cell">
                      {t.dispatched_at ? new Date(t.dispatched_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="hidden px-3 py-2 text-xs text-muted-foreground lg:table-cell">
                      {t.received_at ? new Date(t.received_at).toLocaleDateString() : "—"}
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
