import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useReportRegistry } from "@/lib/queries";

const GROUPS: { title: string; reports: { name: string; label: string; description: string }[] }[] = [
  {
    title: "Sales",
    reports: [
      { name: "daily_sales", label: "Daily sales", description: "Gross / tax / net per day per branch" },
      { name: "hourly_heatmap", label: "Hourly heatmap", description: "Sales density by hour and weekday" },
      { name: "item_wise", label: "Item-wise sales", description: "Quantity, revenue, COGS per product" },
      { name: "category_wise", label: "Category-wise", description: "Sales rolled up by category" },
      { name: "top_movers", label: "Top movers", description: "Best-selling products by revenue" },
      { name: "slow_movers", label: "Slow movers", description: "In-stock items with low velocity" },
      { name: "cashier_performance", label: "Cashier performance", description: "Invoices, gross, avg ticket per cashier" },
      { name: "branch_comparison", label: "Branch comparison", description: "Side-by-side branch metrics" },
    ],
  },
  {
    title: "Inventory & Operations",
    reports: [
      { name: "stock", label: "Stock report", description: "Current quantity per branch with reorder flags" },
      { name: "stock_aging", label: "Stock aging", description: "On-hand inventory bucketed by age" },
      { name: "payment_breakdown", label: "Payment methods", description: "Totals by payment method" },
      { name: "returns_analysis", label: "Returns analysis", description: "Return rate, reasons, FBR routes" },
      { name: "profit_loss", label: "Profit & loss", description: "Revenue, COGS, gross margin per period" },
    ],
  },
  {
    title: "Compliance & Customers",
    reports: [
      { name: "tax", label: "Tax report (FBR)", description: "Tax collected per rate band" },
      { name: "fbr_submissions", label: "FBR submissions", description: "Every PRAL roundtrip with status" },
      { name: "audit_log", label: "Audit log", description: "Append-only history of changes" },
      { name: "customer_top_n", label: "Customer top-N", description: "Biggest spenders" },
      { name: "customer_dormant", label: "Dormant customers", description: "Customers who haven't returned" },
      { name: "supplier_purchase", label: "Supplier purchases", description: "Spend by supplier (purchases module pending)" },
    ],
  },
];

export default function ReportsIndex() {
  const { data, isLoading } = useReportRegistry();
  const known = new Set(data?.results.map((r) => r.name) ?? []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          {isLoading ? "Loading registry…" : `${known.size} reports available.`}
        </p>
      </div>

      {GROUPS.map((group) => (
        <section key={group.title} className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">{group.title}</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {group.reports.map((r) => (
              <Link
                key={r.name}
                to={`/reports/${r.name}`}
                className="block group"
              >
                <Card className="transition-colors hover:bg-accent">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-sm">
                      {r.label}
                      <ChevronRight className="h-4 w-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs text-muted-foreground">
                    {r.description}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
