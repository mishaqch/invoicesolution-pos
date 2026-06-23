import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Elevated surface used for feature/industry/pricing cards. */
export function Card({
  children,
  className,
  hover = true,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-100 bg-white p-6 shadow-card",
        hover && "transition-all duration-200 hover:-translate-y-1 hover:border-brand-200 hover:shadow-glow",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Rounded icon chip in brand colours, used at the top of cards. */
export function IconChip({ children }: { children: ReactNode }) {
  return (
    <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100">
      {children}
    </div>
  );
}
