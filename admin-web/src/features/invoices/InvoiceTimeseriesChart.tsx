/**
 * Bar chart of invoices grouped by time interval.
 *
 * Mirrors the PRAL DI manual v1.6 dashboard (pages 20–21):
 *  - Number of Invoices Generated tile-row at the top.
 *  - Bar chart with two dropdowns: Time Interval (Daily / Monthly /
 *    Quarterly / Yearly) and Invoice Type (Sale / Debit).
 *
 * Pure SVG so we don't pull in another chart library. The data shape
 * matches the backend response from /api/sales/invoices/timeseries/.
 */

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import {
  useInvoiceTimeseries,
  type TimeseriesInterval,
  type TimeseriesInvoiceType,
} from "@/lib/queries";

const INTERVALS: { value: TimeseriesInterval; label: string }[] = [
  { value: "day", label: "Daily" },
  { value: "month", label: "Monthly" },
  { value: "quarter", label: "Quarterly" },
  { value: "year", label: "Yearly" },
];

const INVOICE_TYPES: { value: TimeseriesInvoiceType; label: string }[] = [
  { value: "sale", label: "Sale invoice" },
  { value: "debit_note", label: "Debit note" },
  { value: "credit_note", label: "Credit note" },
];

function fmtRs(value: number): string {
  if (value >= 1_000_000) return `Rs. ${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `Rs. ${(value / 1_000).toFixed(1)}K`;
  return `Rs. ${value.toFixed(0)}`;
}

export function InvoiceTimeseriesChart() {
  const [interval, setInterval] = useState<TimeseriesInterval>("day");
  const [invoiceType, setInvoiceType] =
    useState<TimeseriesInvoiceType>("sale");
  const { data, isLoading } = useInvoiceTimeseries(interval, invoiceType);

  const buckets = data?.buckets ?? [];
  const totalCount = buckets.reduce((s, b) => s + b.count, 0);
  const totalRevenue = buckets.reduce((s, b) => s + Number(b.revenue), 0);

  // Bars: scale to the max revenue in the visible window so even small
  // datasets render readable bars. Count is shown above each bar.
  const maxRevenue = Math.max(1, ...buckets.map((b) => Number(b.revenue) || 0));
  // Cap visible buckets to keep the chart readable; older buckets are
  // dropped from the right side of the rendered range.
  const visible = buckets.slice(-30);
  const W = 640;
  const H = 200;
  const PAD_L = 40;
  const PAD_B = 28;
  const innerW = W - PAD_L - 8;
  const innerH = H - PAD_B - 8;
  const barW = visible.length ? innerW / visible.length - 4 : 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <CardTitle className="text-sm">
              Number of invoices generated
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {totalCount} invoices · {fmtRs(totalRevenue)} total
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={interval}
              onChange={(e) =>
                setInterval(e.target.value as TimeseriesInterval)
              }
              className="h-8 text-xs"
              aria-label="Time interval"
            >
              {INTERVALS.map((i) => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </Select>
            <Select
              value={invoiceType}
              onChange={(e) =>
                setInvoiceType(e.target.value as TimeseriesInvoiceType)
              }
              className="h-8 text-xs"
              aria-label="Invoice type"
            >
              {INVOICE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Loading…
          </p>
        ) : visible.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No invoices in this range.
          </p>
        ) : (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full"
            role="img"
            aria-label={`Invoice count by ${interval}`}
          >
            {/* Y-axis baseline */}
            <line
              x1={PAD_L} y1={H - PAD_B} x2={W} y2={H - PAD_B}
              stroke="currentColor" strokeOpacity={0.15}
            />
            {visible.map((b, i) => {
              const value = Number(b.revenue) || 0;
              const h = (value / maxRevenue) * innerH;
              const x = PAD_L + i * (barW + 4);
              const y = H - PAD_B - h;
              return (
                <g key={`${b.label}-${i}`}>
                  <rect
                    x={x} y={y} width={barW} height={Math.max(h, 1)}
                    rx="2"
                    className="fill-primary"
                    opacity={0.85}
                  >
                    <title>
                      {b.label}: {b.count} invoice
                      {b.count === 1 ? "" : "s"} · Rs. {b.revenue}
                    </title>
                  </rect>
                  {/* Count label above bar (only when there's room) */}
                  {b.count > 0 && barW > 14 && (
                    <text
                      x={x + barW / 2} y={y - 3}
                      textAnchor="middle"
                      className="fill-current text-[9px]"
                      opacity={0.8}
                    >
                      {b.count}
                    </text>
                  )}
                  {/* X-axis label — first, middle, last to avoid clutter */}
                  {(i === 0 || i === visible.length - 1
                    || i === Math.floor(visible.length / 2)) && (
                    <text
                      x={x + barW / 2} y={H - PAD_B + 14}
                      textAnchor="middle"
                      className="fill-current text-[9px]"
                      opacity={0.6}
                    >
                      {b.label}
                    </text>
                  )}
                </g>
              );
            })}
            {/* Y-axis max-revenue label */}
            <text
              x={6} y={12}
              className="fill-current text-[9px]"
              opacity={0.6}
            >
              {fmtRs(maxRevenue)}
            </text>
          </svg>
        )}
      </CardContent>
    </Card>
  );
}
