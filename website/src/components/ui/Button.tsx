import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "white";
type Size = "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-60";

const variants: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white shadow-glow hover:bg-brand-700 hover:-translate-y-0.5 active:translate-y-0",
  secondary:
    "border border-slate-200 bg-white text-ink shadow-soft hover:border-brand-300 hover:text-brand-700",
  ghost: "text-ink-soft hover:bg-slate-100 hover:text-ink",
  white: "bg-white text-brand-700 shadow-soft hover:bg-brand-50",
};

const sizes: Record<Size, string> = {
  md: "h-11 px-5 text-sm",
  lg: "h-13 px-7 text-base py-3.5",
};

interface CommonProps {
  variant?: Variant;
  size?: Size;
  className?: string;
  children: ReactNode;
}

/** Internal route link styled as a button. */
export function ButtonLink({
  to,
  variant = "primary",
  size = "md",
  className,
  children,
}: CommonProps & { to: string }) {
  return (
    <Link to={to} className={cn(base, variants[variant], sizes[size], className)}>
      {children}
    </Link>
  );
}

/** External anchor styled as a button (app login, WhatsApp, tel:). */
export function ButtonAnchor({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
  external = true,
}: CommonProps & { href: string; external?: boolean }) {
  return (
    <a
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      className={cn(base, variants[variant], sizes[size], className)}
    >
      {children}
    </a>
  );
}

/** Plain <button> (form submit, toggles). */
export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  type = "button",
  disabled,
  onClick,
}: CommonProps & {
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn(base, variants[variant], sizes[size], className)}
    >
      {children}
    </button>
  );
}
