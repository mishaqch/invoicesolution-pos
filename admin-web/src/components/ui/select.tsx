import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Native <select> wrapped to match shadcn primitives. We avoid the Radix
 * dropdown variant for now — Phase 1 has many forms, native is plenty.
 *
 * Shares the same focus / hover / invalid treatment as Input so forms
 * read as one consistent system regardless of field type.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        // Base
        "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm",
        "transition-colors",
        // Hover / focus / invalid — mirrors Input.
        "hover:border-slate-300 dark:hover:border-slate-600",
        "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:border-primary",
        "aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive/30",
        // Disabled
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-muted",
        // Custom arrow — appear consistent across OSes
        "appearance-none bg-[length:16px_16px] bg-[right_0.65rem_center] bg-no-repeat pr-8",
        "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22 fill=%22none%22 stroke=%22currentColor%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><polyline points=%226 9 12 15 18 9%22/></svg>')]",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";
