import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFbrCancelBudget } from "@/lib/queries";

function pct(consumed: string, budget: string) {
  const c = parseFloat(consumed) || 0;
  const b = parseFloat(budget) || 0;
  if (b <= 0) return 0;
  return Math.min(100, (c / b) * 100);
}

function daysUntilNextMonth(): number {
  const now = new Date();
  const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return Math.ceil((next.getTime() - now.getTime()) / (24 * 60 * 60 * 1000));
}

export default function CancelBudgetPage() {
  const { data: budget, isLoading } = useFbrCancelBudget();

  if (isLoading || !budget) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  const fillPct = pct(budget.consumed_amount, budget.budget_amount);
  const isHighConsumption = fillPct >= 80;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Cancel budget</h1>
        <p className="text-sm text-muted-foreground">
          The 10% monthly cap on cancellations and edits combined. Resets in
          {" "}{daysUntilNextMonth()} days.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Month of {new Date(budget.month_start).toLocaleDateString(undefined, {
              year: "numeric", month: "long",
            })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <Stat
              label="Last month's sales"
              value={`Rs ${parseFloat(budget.previous_month_sales).toFixed(2)}`}
            />
            <Stat
              label="Budget (10%)"
              value={`Rs ${parseFloat(budget.budget_amount).toFixed(2)}`}
            />
            <Stat
              label="Remaining"
              value={`Rs ${parseFloat(budget.remaining_amount).toFixed(2)}`}
              tone={isHighConsumption ? "amber" : "default"}
            />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
              <span>Consumed: Rs {parseFloat(budget.consumed_amount).toFixed(2)}</span>
              <span>{fillPct.toFixed(1)}%</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full ${
                  fillPct >= 100 ? "bg-red-500" : fillPct >= 80 ? "bg-amber-500" : "bg-primary"
                }`}
                style={{ width: `${fillPct}%` }}
              />
            </div>
            {isHighConsumption && fillPct < 100 && (
              <p className="mt-2 text-xs text-amber-700">
                Heads up: you've used over 80% of this month's budget. Once
                exhausted, future cancellations must use credit notes instead.
              </p>
            )}
            {fillPct >= 100 && (
              <p className="mt-2 text-xs text-destructive">
                Budget exhausted. Cancellations are blocked until next month;
                use a credit note (Phase 6) instead.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Consumption history</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Invoice</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {budget.consumptions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    No consumptions this month.
                  </TableCell>
                </TableRow>
              ) : (
                budget.consumptions.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(c.consumed_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="capitalize">{c.consumption_type}</TableCell>
                    <TableCell className="text-right font-mono">
                      Rs {parseFloat(c.amount).toFixed(2)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {c.invoice.slice(0, 8)}…
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  label, value, tone = "default",
}: { label: string; value: string; tone?: "default" | "amber" }) {
  return (
    <div className="rounded-md border p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-xl ${tone === "amber" ? "text-amber-700" : ""}`}>
        {value}
      </div>
    </div>
  );
}
