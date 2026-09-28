import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Minimal shadcn-style button primitive (copied from admin-web, retinted to
 * the Lakeside tokens). Most of the tablet's surfaces use the hand-written
 * artifact classes directly; this is here for the few generic buttons.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "rounded-[14px] text-sm font-bold cursor-pointer",
    "transition-all duration-150",
    "focus-visible:outline-none",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-[var(--lake)] text-white shadow-[var(--shadow-sm)] hover:bg-[var(--lake-deep)]",
        outline:
          "border border-[var(--line)] bg-[var(--card)] text-[var(--ink)] hover:border-[var(--lake)] hover:text-[var(--lake)]",
        ghost: "hover:bg-[var(--lake-mist)] text-[var(--ink)]",
      },
      size: {
        default: "h-11 px-5 py-2",
        sm: "h-9 px-3 text-xs",
        lg: "h-12 px-6 text-base",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

// eslint-disable-next-line react-refresh/only-export-components
export { buttonVariants };
