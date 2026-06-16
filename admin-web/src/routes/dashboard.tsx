import {
  AlertCircle, ArrowUpRight, Boxes, Package, Receipt, Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsDigitalInvoicing } from "@/features/modules/hooks";
import { InvoiceTimeseriesChart } from "@/features/invoices/InvoiceTimeseriesChart";
import { OnboardingWizard } from "@/features/onboarding/Wizard";
import { useDashboard, useTenantSetup, type DashboardData } from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";

function formatRs(amount: string | number): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  return `Rs. ${n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Compact money for cards: Rs 1.34M / Rs 12.5k / Rs 940.
function formatRsCompact(amount: string | number): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `Rs ${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `Rs ${(n / 1_000).toFixed(1)}k`;
  return `Rs ${n.toLocaleString("en-PK", { maximumFractionDigits: 0 })}`;
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
    <svg width={w} height={h} className="overflow-visible text-primary" role="img" aria-label="7-day sales trend">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/**
 * Overview stat card. An accessible link to the relevant section, with a
 * primary value, a secondary hint line, and a tinted icon. Hover/focus lift
 * + a visible focus ring (WCAG 2.4.13).
 */
function StatCard({
  to, label, value, hint, icon: Icon, tone = "neutral",
}: {
  to: string;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  tone?: "neutral" | "primary" | "warning";
}) {
  const iconTone =
    tone === "warning" ? "bg-warning-soft text-warning-soft-foreground"
    : tone === "primary" ? "bg-primary-soft text-primary-soft-foreground"
    : "bg-muted text-muted-foreground";
  return (
    <Link
      to={to}
      className="group flex flex-col justify-between rounded-xl border bg-card p-4 shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
    >
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${iconTone}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-3">
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
      </div>
      <span className="mt-2 inline-flex items-center gap-0.5 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        View <ArrowUpRight className="h-3 w-3" />
      </span>
    </Link>
  );
}

/** The mode-aware entity overview row. */
function OverviewCards({ totals, di }: { totals: NonNullable<DashboardData["totals"]>; di: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatCard
        to="/catalog/products" label="Products" icon={Package} tone="primary"
        value={totals.products_active.toLocaleString("en-PK")}
        hint="Active products"
      />
      <StatCard
        to="/customers" label="Customers" icon={Users}
        value={totals.customers.toLocaleString("en-PK")}
        hint="On file"
      />
      <StatCard
        to="/sales" label="Invoices" icon={Receipt} tone="primary"
        value={totals.invoices_total.toLocaleString("en-PK")}
        hint={
          totals.invoices_month_count > 0
            ? `${totals.invoices_month_count} this month · ${formatRsCompact(totals.invoices_month_gross)}`
            : "Validated total"
        }
      />
      {/* Stock card: DI links to warehouse stock, POS to stock-by-branch. */}
      <StatCard
        to={di ? "/inventory/warehouse-stock" : "/inventory/stock"}
        label="Stock"
        icon={Boxes}
        tone={totals.low_stock_count > 0 ? "warning" : "neutral"}
        value={totals.stock_items.toLocaleString("en-PK")}
        hint={
          totals.low_stock_count > 0
            ? `${totals.low_stock_count} low · ${formatRsCompact(totals.stock_value)} value`
            : `${formatRsCompact(totals.stock_value)} value`
        }
      />
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card p-4 shadow-xs">
          <div className="flex items-start justify-between">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-8 w-8 rounded-lg" />
          </div>
          <Skeleton className="mt-4 h-7 w-20" />
          <Skeleton className="mt-2 h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

export default function DashboardRoute() {
  const user = useAuthStore((s) => s.user);
  const tenant = useAuthStore((s) => s.tenant);
  const { data, isLoading } = useDashboard();
  const { data: setup } = useTenantSetup();
  const di = useIsDigitalInvoicing();

  // DI tenants have no till — relabel the POS-flavoured daily KPI tiles with
  // what the back-office operator cares about. Same numbers, different framing.
  const isDigitalOnly = setup?.business_mode === "digital_invoicing";
  const tileLabels = isDigitalOnly
    ? { gross: "Invoices today", count: "Sent to FBR", avg: "Avg invoice", fourth: "Pending validation" }
    : { gross: "Today gross", count: "Invoices", avg: "Avg ticket", fourth: "Returns today" };

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

      <OnboardingWizard />

      {/* ── Entity overview cards (Products / Customers / Invoices / Stock) ── */}
      {isLoading || !data ? (
        <OverviewSkeleton />
      ) : data.totals ? (
        <OverviewCards totals={data.totals} di={di} />
      ) : null}

      {isLoading || !data ? (
        <DailyKpiSkeleton />
      ) : (
        <>
          {/* Daily KPI strip. */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTile label={tileLabels.gross} value={formatRs(data.kpis.today_gross)} extra={<Sparkline points={data.sparkline} />} />
            <KpiTile label={tileLabels.count} value={String(data.kpis.today_count)} />
            <KpiTile label={tileLabels.avg} value={formatRs(data.kpis.avg_ticket)} />
            <KpiTile label={tileLabels.fourth} value={String(data.kpis.today_refunds)} />
          </div>

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
                  <Link to="/sales" className="text-xs text-muted-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded">
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
                          <td className="px-3 py-2 text-right">{s.quantity} / {s.reorder_level}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="border-t p-2 text-right">
                  <Link to={di ? "/inventory/warehouse-stock" : "/inventory/stock"} className="text-xs text-muted-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded">
                    Manage stock →
                  </Link>
                </div>
              </CardContent>
            </Card>

            {/* Payment mix is a till concept — hide for Digital-Invoicing. */}
            {!isDigitalOnly && (
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
            )}

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
                  <Link to="/fbr/submissions" className="text-xs text-muted-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded">
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

function KpiTile({ label, value, extra }: { label: string; value: string; extra?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {extra}
      </CardContent>
    </Card>
  );
}

function DailyKpiSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-lg border bg-card p-4 shadow-xs">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-3 h-7 w-24" />
        </div>
      ))}
    </div>
  );
}
