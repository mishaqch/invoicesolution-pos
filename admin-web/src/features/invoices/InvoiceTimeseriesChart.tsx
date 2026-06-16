/**
 * Bar chart of sales (revenue) grouped by time interval.
 *
 * Mirrors the PRAL DI manual v1.6 dashboard (pages 20-21): a bar chart with
 * two dropdowns — Time Interval (Daily / Monthly / Quarterly / Yearly) and
 * Invoice Type (Sale / Debit / Credit). Bar HEIGHT = revenue for the period;
 * the invoice count + exact revenue show on hover.
 *
 * Pure SVG (no chart library): width-capped + centred bars so a single data
 * point doesn't stretch across the whole chart, horizontal gridlines with
 * Y-axis money ticks, readable labels, an interactive hover highlight, and a
 * brand-tinted gradient fill. Fully theme-token + keyboard/SR accessible.
 */

import { useId, useMemo, useState } from "react";

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
  if (value >= 1_000_000) return `Rs ${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `Rs ${(value / 1_000).toFixed(1)}K`;
  return `Rs ${value.toFixed(0)}`;
}

// A "nice" round number >= v, for the top gridline (e.g. 330 -> 400, 4500 -> 5000).
function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * mag;
}

export function InvoiceTimeseriesChart() {
  const [interval, setInterval] = useState<TimeseriesInterval>("day");
  const [invoiceType, setInvoiceType] = useState<TimeseriesInvoiceType>("sale");
  const [hover, setHover] = useState<number | null>(null);
  const gradientId = useId();
  const { data, isLoading } = useInvoiceTimeseries(interval, invoiceType);

  const buckets = data?.buckets ?? [];
  const totalCount = buckets.reduce((s, b) => s + b.count, 0);
  const totalRevenue = buckets.reduce((s, b) => s + Number(b.revenue), 0);
  const visible = useMemo(() => buckets.slice(-30), [buckets]);

  // ── Geometry ──────────────────────────────────────────────────────────
  const W = 720;
  const H = 240;
  const PAD_L = 56;   // room for Y-axis money ticks
  const PAD_R = 16;
  const PAD_T = 16;
  const PAD_B = 32;   // room for X-axis date labels
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const baseY = PAD_T + innerH;

  // Round the scale to a nice top so the gridlines read cleanly.
  const rawMax = Math.max(0, ...visible.map((b) => Number(b.revenue) || 0));
  const maxVal = niceCeil(rawMax || 1);

  // Slot per bucket; bar is centred in its slot and WIDTH-CAPPED so a single
  // data point shows a tidy column instead of one giant full-width bar.
  const slot = visible.length ? innerW / visible.length : innerW;
  const barW = Math.min(slot * 0.62, 48);

  const gridLines = 4; // horizontal gridlines incl. top (0 is the axis)
  const ticks = Array.from({ length: gridLines + 1 }, (_, i) => (maxVal / gridLines) * i);

  // Label every Nth bucket so they don't collide (target ~8 labels).
  const labelEvery = Math.max(1, Math.ceil(visible.length / 8));

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <CardTitle className="text-sm">Sales over time</CardTitle>
            <p className="text-xs text-muted-foreground">
              {totalCount} invoice{totalCount === 1 ? "" : "s"} · {fmtRs(totalRevenue)} total
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={interval}
              onChange={(e) => setInterval(e.target.value as TimeseriesInterval)}
              className="h-8 text-xs" aria-label="Time interval"
            >
              {INTERVALS.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
            </Select>
            <Select
              value={invoiceType}
              onChange={(e) => setInvoiceType(e.target.value as TimeseriesInvoiceType)}
              className="h-8 text-xs" aria-label="Invoice type"
            >
              {INVOICE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
            Loading…
          </div>
        ) : visible.length === 0 ? (
          <div className="flex h-[200px] flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
            <span>No invoices in this range.</span>
            <span className="text-xs">Create an invoice to see it here.</span>
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full"
            role="img"
            aria-label={`Sales by ${interval}: ${totalCount} invoices totalling ${fmtRs(totalRevenue)}`}
            onMouseLeave={() => setHover(null)}
          >
            <defs>
              {/* Stops carry the brand color via the `text-primary` class so
                  the gradient re-themes with the design tokens. Setting the
                  class on each stop (not relying on currentColor inheritance
                  into <defs>, which browsers handle inconsistently). */}
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" className="text-primary" stopColor="currentColor" stopOpacity={0.95} />
                <stop offset="100%" className="text-primary" stopColor="currentColor" stopOpacity={0.5} />
              </linearGradient>
            </defs>

            {/* Horizontal gridlines + Y-axis money ticks. */}
            {ticks.map((t, i) => {
              const y = baseY - (t / maxVal) * innerH;
              return (
                <g key={i}>
                  <line
                    x1={PAD_L} y1={y} x2={W - PAD_R} y2={y}
                    stroke="currentColor"
                    strokeOpacity={i === 0 ? 0.25 : 0.08}
                  />
                  <text
                    x={PAD_L - 8} y={y + 3} textAnchor="end"
                    className="fill-muted-foreground text-[10px]"
                  >
                    {fmtRs(t)}
                  </text>
                </g>
              );
            })}

            {/* Bars. */}
            {visible.map((b, i) => {
              const value = Number(b.revenue) || 0;
              const h = maxVal > 0 ? (value / maxVal) * innerH : 0;
              const x = PAD_L + i * slot + (slot - barW) / 2;
              const y = baseY - h;
              const active = hover === i;
              return (
                <g
                  key={`${b.label}-${i}`}
                  onMouseEnter={() => setHover(i)}
                >
                  {/* Full-height hover hit area + highlight band. */}
                  <rect
                    x={PAD_L + i * slot} y={PAD_T} width={slot} height={innerH}
                    className={active ? "fill-primary" : "fill-transparent"}
                    opacity={active ? 0.06 : 0}
                  />
                  <rect
                    x={x} y={y} width={barW} height={Math.max(h, value > 0 ? 2 : 0)}
                    rx="3"
                    className="text-primary"
                    fill={`url(#${gradientId})`}
                    opacity={hover === null || active ? 1 : 0.55}
                    style={{ transition: "opacity 120ms" }}
                  >
                    <title>
                      {b.label}: {fmtRs(value)} · {b.count} invoice{b.count === 1 ? "" : "s"}
                    </title>
                  </rect>
                  {/* Value label above the hovered bar. */}
                  {active && value > 0 && (
                    <text
                      x={x + barW / 2} y={y - 6} textAnchor="middle"
                      className="fill-foreground text-[11px] font-medium"
                    >
                      {fmtRs(value)}
                    </text>
                  )}
                  {/* X-axis date label (every Nth, plus the last). */}
                  {(i % labelEvery === 0 || i === visible.length - 1) && (
                    <text
                      x={x + barW / 2} y={baseY + 16} textAnchor="middle"
                      className="fill-muted-foreground text-[10px]"
                    >
                      {b.label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </CardContent>
    </Card>
  );
}
