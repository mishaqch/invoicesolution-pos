import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Standard page header: a title (+ optional subtitle) on the left and optional
 * actions on the right. Stacks vertically on mobile and goes side-by-side from
 * `sm` up, so the title + action buttons never squish on a phone. Use on every
 * list/detail page in place of an ad-hoc `flex justify-between` row.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {typeof title === "string" ? (
          <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        ) : (
          title
        )}
        {subtitle && (
          <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{actions}</div>
      )}
    </div>
  );
}
