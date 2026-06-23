import { jsx as _jsx } from "react/jsx-runtime";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
const base = "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-60";
const variants = {
    primary: "bg-brand-600 text-white shadow-glow hover:bg-brand-700 hover:-translate-y-0.5 active:translate-y-0",
    secondary: "border border-slate-200 bg-white text-ink shadow-soft hover:border-brand-300 hover:text-brand-700",
    ghost: "text-ink-soft hover:bg-slate-100 hover:text-ink",
    white: "bg-white text-brand-700 shadow-soft hover:bg-brand-50",
};
const sizes = {
    md: "h-11 px-5 text-sm",
    lg: "h-13 px-7 text-base py-3.5",
};
/** Internal route link styled as a button. */
export function ButtonLink({ to, variant = "primary", size = "md", className, children, }) {
    return (_jsx(Link, { to: to, className: cn(base, variants[variant], sizes[size], className), children: children }));
}
/** External anchor styled as a button (app login, WhatsApp, tel:). */
export function ButtonAnchor({ href, variant = "primary", size = "md", className, children, external = true, }) {
    return (_jsx("a", { href: href, ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}), className: cn(base, variants[variant], sizes[size], className), children: children }));
}
/** Plain <button> (form submit, toggles). */
export function Button({ variant = "primary", size = "md", className, children, type = "button", disabled, onClick, }) {
    return (_jsx("button", { type: type, disabled: disabled, onClick: onClick, className: cn(base, variants[variant], sizes[size], className), children: children }));
}
