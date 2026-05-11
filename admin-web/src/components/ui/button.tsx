import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // Base — every button gets the same focus ring, transition, and disabled treatment.
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "rounded-md text-sm font-medium",
    "ring-offset-background transition-all duration-150",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        // Brand primary — emerald-600, deeper on hover, subtle lift via shadow.
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover hover:shadow-md active:shadow-sm",
        // Hard red for destructive — same lift treatment.
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90 hover:shadow-md",
        // Outline — neutral bg, brand-tinted hover.
        outline:
          "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground hover:border-primary/40",
        // Soft chip — for low-emphasis actions inside cards.
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        // No background until hover — for icon-only buttons inside dense rows.
        ghost: "hover:bg-accent hover:text-accent-foreground",
        // Pure text — for "View all" style links.
        link: "text-primary underline-offset-4 hover:underline",
        // Brand-tinted soft pill — for secondary brand CTAs (e.g. "Filter").
        soft:
          "bg-primary-soft text-primary-soft-foreground hover:bg-primary-soft/70",
      },
      size: {
        sm: "h-8 rounded-md px-3 text-xs",
        default: "h-10 px-4 py-2",
        lg: "h-11 rounded-md px-6 text-base",
        // Compact icon-only — perfectly square so SVG centers.
        icon: "h-10 w-10",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** When true, disables the button and shows a spinner before children.
   *  Use for async-mutation CTAs (Save, Submit, etc.) so users see the
   *  click registered without us having to wire a spinner manually. */
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    // Radix <Slot> (asChild mode) demands React.Children.only — so we
    // can't inject the loading spinner alongside children. asChild is
    // typically used to render a <Link>, where a spinner doesn't apply
    // anyway; consumers needing a spinner should use the regular
    // <button>-rendering form.
    const content = !asChild && loading ? (
      <>
        <Loader2 className="animate-spin" aria-hidden />
        {children}
      </>
    ) : (
      children
    );

    return (
      <Comp
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        disabled={!asChild && (disabled || loading)}
        {...props}
      >
        {content}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
