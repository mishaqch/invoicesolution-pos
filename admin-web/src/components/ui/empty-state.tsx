import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Empty state — used when a list / table has no results.
 *
 * Pass an icon, a one-line title, optional description, and an optional
 * primary action. Sits inside whatever container you put it in (Card,
 * TableCell colSpan, etc.).
 *
 * Example:
 *   <EmptyState
 *     icon={<Receipt className="h-12 w-12" />}
 *     title="No invoices yet"
 *     description="Create your first invoice to get started."
 *     action={<Button>New invoice</Button>}
 *   />
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <div className="rounded-full bg-primary-soft p-3 text-primary-soft-foreground">
          {icon}
        </div>
      )}
      <div className="space-y-1">
        <h3 className="text-base font-semibold">{title}</h3>
        {description && (
          <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
