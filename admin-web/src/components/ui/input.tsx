import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Input — base text field used everywhere.
 *
 * Focus: 2px brand ring with 2px offset (meets WCAG 2.2 SC 2.4.13).
 * Hover: subtle border tint so users know it's interactive.
 * Invalid: when the input has `aria-invalid="true"` or matches :invalid,
 *          the border + ring flip to destructive — pair with a sibling
 *          error message for accessible field-level errors.
 */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        // Base shape
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
        // File input affordances
        "file:border-0 file:bg-transparent file:text-sm file:font-medium",
        // Placeholder
        "placeholder:text-muted-foreground",
        // Smooth transitions on border + ring color changes
        "transition-colors",
        // Hover — subtle border deepen so the field reads as actionable
        "hover:border-slate-300 dark:hover:border-slate-600",
        // Focus
        "ring-offset-background focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:border-primary",
        // Invalid
        "aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive/30",
        // Disabled
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-muted",
        // Native date/time pickers get a small icon-tint nudge
        "[&::-webkit-calendar-picker-indicator]:cursor-pointer",
        "[&::-webkit-calendar-picker-indicator]:opacity-60",
        "[&::-webkit-calendar-picker-indicator]:hover:opacity-100",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";
