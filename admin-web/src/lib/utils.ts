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
