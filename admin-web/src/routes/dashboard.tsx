import { AlertCircle, Package, Receipt } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InvoiceTimeseriesChart } from "@/features/invoices/InvoiceTimeseriesChart";
import { OnboardingWizard } from "@/features/onboarding/Wizard";
import { useDashboard, useTenantSetup } from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";

function formatRs(amount: string): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return amount;
  return `Rs. ${n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function freshness(ts: string | null): string {
  if (!ts) return "Never";
  const built = new Date(ts).getTime();
  const diff = Math.max(0, Date.now() - built);
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "Just now";
  if (min < 60) return `${min} min ago`;
  return `${Math.floor(min / 60)}h ${min % 60}m ago`;
}

function Sparkline({ points }: { points: { date: string; gross: string }[] }) {
  if (points.length === 0) return null;
  const values = points.map((p) => Number(p.gross) || 0);
  const max = Math.max(...values, 1);
  const w = 200;
  const h = 36;
  const step = w / Math.max(1, values.length - 1);
  const path = values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${i * step} ${h - (v / max) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export default function DashboardRoute() {
  const user = useAuthStore((s) => s.user);
  const tenant = useAuthStore((s) => s.tenant);
  const { data, isLoading } = useDashboard();
  const { data: setup } = useTenantSetup();

  // Digital-Invoicing tenants don't have a till — relabel the POS-
  // flavoured KPI tiles ("Today gross", "Returns today") with what
  // the back-office operator actually cares about. The underlying
  // numbers come from the same endpoint; only the framing changes.
  const isDigitalOnly = setup?.business_mode === "digital_invoicing";
  const tileLabels = isDigitalOnly
    ? {
      gross: "Invoices today",
      count: "Sent to FBR",
      avg: "Avg invoice",
      fourth: "Pending validation",
    }
    : {
      gross: "Today gross",
      count: "Invoices",
      avg: "Avg ticket",
      fourth: "Returns today",
    };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome{user ? `, ${user.full_name}` : ""}.
          </h1>
          <p className="text-sm text-muted-foreground">
            Signed in to {tenant?.business_name ?? "—"}.
          </p>
        </div>
        {data && (
          <p className="text-xs text-muted-foreground">
            Updated {freshness(data.freshness.last_built_at)}
          </p>
        )}
      </div>

      {/* SetupWizard removed: business_mode + FBR taxonomy are set
          by the platform super-admin at tenant creation, not by the
          tenant operator. Tenants get a pre-configured environment
          appropriate for their plan (POS / IMS or Digital Invoicing). */}

      <OnboardingWizard />

      {isLoading || !data ? (
        <p className="text-sm text-muted-foreground">Loading dashboard…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  {tileLabels.gross}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">{formatRs(data.kpis.today_gross)}</div>
                <Sparkline points={data.sparkline} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  {tileLabels.count}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">{data.kpis.today_count}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  {tileLabels.avg}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">{formatRs(data.kpis.avg_ticket)}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  {tileLabels.fourth}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">{data.kpis.today_refunds}</div>
              </CardContent>
            </Card>
          </div>

          {/* FBR-style invoice bar chart — daily/monthly/quarterly/yearly,
              sale vs debit/credit note. Matches PRAL DI manual §4.1.2 §2.1. */}
          <InvoiceTimeseriesChart />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Receipt className="h-4 w-4" /> Recent invoices
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.recent_invoices.length === 0 ? (
                  <p className="p-4 text-sm text-muted-foreground">No invoices yet today.</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody>
                      {data.recent_invoices.map((i) => (
                        <tr key={i.id} className="border-b last:border-0 hover:bg-muted/30">
                          <td className="px-3 py-2 font-mono">{i.local_invoice_number}</td>
                          <td className="px-3 py-2 text-muted-foreground">{i.branch}</td>
                          <td className="px-3 py-2 text-right font-medium">{formatRs(i.grand_total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="border-t p-2 text-right">
                  <Link to="/sales" className="text-xs text-muted-foreground hover:underline">
                    All sales →
                  </Link>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Package className="h-4 w-4" /> Low stock
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.low_stock.length === 0 ? (
                  <p className="p-4 text-sm text-muted-foreground">All stock levels healthy.</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody>
                      {data.low_stock.map((s, idx) => (
                        <tr key={idx} className="border-b last:border-0">
                          <td className="px-3 py-2 font-mono text-xs">{s.sku}</td>
                          <td className="px-3 py-2">{s.name}</td>
                          <td className="px-3 py-2 text-right">
                            {s.quantity} / {s.reorder_level}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Today&apos;s payment mix</CardTitle>
              </CardHeader>
              <CardContent>
                {data.payment_breakdown.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No payments yet today.</p>
                ) : (
                  <ul className="space-y-2">
                    {data.payment_breakdown.map((p) => {
                      const total = data.payment_breakdown.reduce((acc, q) => acc + Number(q.total), 0);
                      const pct = total > 0 ? (Number(p.total) / total) * 100 : 0;
                      return (
                        <li key={p.method} className="text-sm">
                          <div className="flex justify-between">
                            <span className="capitalize">{p.method.replace(/_/g, " ")}</span>
                            <span className="font-mono">{formatRs(p.total)}</span>
                          </div>
                          <div className="h-1 rounded-full bg-muted">
                            <div className="h-1 rounded-full bg-primary" style={{ width: `${pct}%` }} />
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <AlertCircle className="h-4 w-4 text-amber-600" /> Failed FBR submissions
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.failed_fbr.length === 0 ? (
                  <p className="p-4 text-sm text-muted-foreground">No recent failures.</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody>
                      {data.failed_fbr.map((f) => (
                        <tr key={f.id} className="border-b last:border-0">
                          <td className="px-3 py-2 font-mono text-xs">{f.invoice_number}</td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">{f.error || f.status_code}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="border-t p-2 text-right">
                  <Link to="/fbr/submissions" className="text-xs text-muted-foreground hover:underline">
                    View all →
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
