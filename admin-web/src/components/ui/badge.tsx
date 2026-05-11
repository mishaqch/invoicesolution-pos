import { cva, type VariantProps } from "class-variance-authority";
import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Badge — small status pill.
 *
 * Variants:
 *   default      — strong brand fill (use sparingly; for highlights)
 *   secondary    — neutral chip (counts, plain labels)
 *   outline      — bordered, no fill (the cleanest look in dense tables)
 *   destructive  — for hard errors / failed states
 *   success      — emerald soft — for "valid", "active", positive states
 *   warning      — amber soft — for "pending", "needs attention"
 *   info         — blue soft — for neutral status, drafts
 *   muted        — grey soft — for inactive / archived
 *
 * The "soft" status variants use background + foreground from the same
 * token family so contrast stays consistent in both light and dark mode.
 */
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground",
        outline:
          "text-foreground",
        destructive:
          "border-transparent bg-destructive-soft text-destructive-soft-foreground",
        success:
          "border-transparent bg-success-soft text-success-soft-foreground",
        warning:
          "border-transparent bg-warning-soft text-warning-soft-foreground",
        info:
          "border-transparent bg-info-soft text-info-soft-foreground",
        muted:
          "border-transparent bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
