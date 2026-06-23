import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
/** Brand lockup: emerald receipt mark + wordmark. Matches the app's identity. */
export function Logo({ className, light = false }) {
    return (_jsxs(Link, { to: "/", className: cn("inline-flex items-center gap-2.5", className), "aria-label": "InvoiceSolution home", children: [_jsx("span", { className: "inline-flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 shadow-sm", children: _jsx("svg", { viewBox: "0 0 64 64", className: "h-5 w-5", "aria-hidden": true, children: _jsxs("g", { fill: "none", stroke: "#ffffff", strokeWidth: "3.5", strokeLinecap: "round", strokeLinejoin: "round", children: [_jsx("path", { d: "M16 8v48l5-2.5L26 56l5-2.5L36 56l5-2.5L46 56l5-2.5V8l-5 2.5L41 8l-5 2.5L31 8l-5 2.5L21 8z" }), _jsx("path", { d: "M40 22h-15a4.5 4.5 0 1 0 0 9h10a4.5 4.5 0 1 1 0 9H22" }), _jsx("path", { d: "M31 41V17" })] }) }) }), _jsxs("span", { className: cn("text-lg font-extrabold tracking-tight", light ? "text-white" : "text-ink"), children: ["Invoice", _jsx("span", { className: "text-brand-600", children: "Solution" })] })] }));
}
