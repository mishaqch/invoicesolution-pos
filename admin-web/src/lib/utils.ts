import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a money value for DISPLAY at 2 decimals with thousands separators.
 * Backend stores DECIMAL(14,4) so raw values look like "1234.0000" — show
 * "1,234.00". Use for any rendered amount; keep raw 4dp strings only in form
 * inputs (NumberInput) where the user edits them.
 */
export function money(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "0.00";
  return n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * Format a QUANTITY (stock on-hand, opening, line qty, ledger balance) at 2
 * decimals. Backend stores quantities as DECIMAL(14,4) so raw values look like
 * "500.0000" — show "500.00". Like money() but without currency framing.
 * Pass-through for null/blank so callers can render their own "—".
 */
export function qty(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
