import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Initials for an avatar (e.g. "Ahmed Khan" -> "AK"). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Relative "x min ago" from an ISO timestamp or epoch ms. */
export function ago(ts: string | number | null | undefined): string {
  if (ts === null || ts === undefined) return "";
  const t = typeof ts === "number" ? ts : Date.parse(ts);
  if (!Number.isFinite(t)) return "";
  const m = Math.round((Date.now() - t) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}
