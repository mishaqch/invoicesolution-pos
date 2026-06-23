import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";

/** Brand lockup: emerald receipt mark + wordmark. Matches the app's identity. */
export function Logo({ className, light = false }: { className?: string; light?: boolean }) {
  return (
    <Link to="/" className={cn("inline-flex items-center gap-2.5", className)} aria-label="InvoiceSolution home">
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 shadow-sm">
        <svg viewBox="0 0 64 64" className="h-5 w-5" aria-hidden>
          <g fill="none" stroke="#ffffff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 8v48l5-2.5L26 56l5-2.5L36 56l5-2.5L46 56l5-2.5V8l-5 2.5L41 8l-5 2.5L31 8l-5 2.5L21 8z" />
            <path d="M40 22h-15a4.5 4.5 0 1 0 0 9h10a4.5 4.5 0 1 1 0 9H22" />
            <path d="M31 41V17" />
          </g>
        </svg>
      </span>
      <span className={cn("text-lg font-extrabold tracking-tight", light ? "text-white" : "text-ink")}>
        Invoice<span className="text-brand-600">Solution</span>
      </span>
    </Link>
  );
}
