import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Reveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/cn";
import { PLANS } from "@/data/plans";
function rs(n) {
    return n.toLocaleString("en-PK");
}
/** Pricing cards with a monthly/yearly toggle. Reused on Home + Pricing. */
export function PricingCards({ compact = false }) {
    const [yearly, setYearly] = useState(false);
    return (_jsxs("div", { children: [_jsx("div", { className: "mb-10 flex items-center justify-center", children: _jsxs("div", { className: "inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-soft", children: [_jsx(ToggleBtn, { active: !yearly, onClick: () => setYearly(false), children: "Monthly" }), _jsxs(ToggleBtn, { active: yearly, onClick: () => setYearly(true), children: ["Yearly", _jsx("span", { className: "ml-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-bold text-brand-700", children: "~2 months free" })] })] }) }), _jsx("div", { className: "grid items-stretch gap-6 lg:grid-cols-3", children: PLANS.map((plan, i) => {
                    const price = yearly ? plan.yearly : plan.monthly;
                    const period = yearly ? "/year" : "/month";
                    return (_jsx(Reveal, { delay: i * 0.08, children: _jsxs("div", { className: cn("relative flex h-full flex-col rounded-2xl border bg-white p-7 shadow-card", plan.highlight ? "border-brand-300 ring-2 ring-brand-200" : "border-slate-100"), children: [plan.highlight && (_jsx("span", { className: "absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-1 text-xs font-bold text-white shadow-sm", children: "Most popular" })), _jsx("h3", { className: "text-lg font-bold text-ink", children: plan.name }), _jsx("p", { className: "mt-1 text-sm text-ink-muted", children: plan.tagline }), _jsxs("div", { className: "mt-5 flex items-end gap-1", children: [_jsx("span", { className: "text-sm font-semibold text-ink-muted", children: "Rs" }), _jsx("span", { className: "text-4xl font-extrabold tracking-tight text-ink", children: rs(price) }), _jsx("span", { className: "pb-1 text-sm text-ink-muted", children: period })] }), _jsx(Link, { to: "/contact", className: cn("mt-6 inline-flex h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition-all", plan.highlight
                                        ? "bg-brand-600 text-white shadow-glow hover:bg-brand-700"
                                        : "border border-slate-200 text-ink hover:border-brand-300 hover:text-brand-700"), children: plan.cta }), !compact && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "mt-6 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs text-ink-soft", children: [_jsx("span", { children: plan.limits.branches }), _jsx("span", { children: plan.limits.terminals }), _jsx("span", { children: plan.limits.products }), _jsx("span", { children: plan.limits.users })] }), _jsx("ul", { className: "mt-6 space-y-3", children: plan.features.map((f) => (_jsxs("li", { className: "flex items-start gap-2.5 text-sm text-ink-soft", children: [_jsx(Check, { className: "mt-0.5 h-4 w-4 shrink-0 text-brand-600" }), _jsx("span", { children: f })] }, f))) })] }))] }) }, plan.name));
                }) }), _jsxs("p", { className: "mt-8 text-center text-sm text-ink-muted", children: ["All prices in PKR. 14-day trial on new accounts. Need something custom?", " ", _jsx(Link, { to: "/contact", className: "font-semibold text-brand-700 hover:underline", children: "Talk to us" }), "."] })] }));
}
function ToggleBtn({ active, onClick, children, }) {
    return (_jsx("button", { type: "button", onClick: onClick, className: cn("inline-flex items-center rounded-full px-4 py-2 text-sm font-medium transition-colors", active ? "bg-brand-600 text-white" : "text-ink-soft hover:text-ink"), children: children }));
}
