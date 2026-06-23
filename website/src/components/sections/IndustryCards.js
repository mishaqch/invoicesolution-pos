import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { INDUSTRIES } from "@/data/industries";
/** Grid of industry cards linking into the Industries page anchors. */
export function IndustryCards({ heading = true }) {
    return (_jsxs("div", { className: "container section", children: [heading && (_jsx(SectionHeading, { eyebrow: "Built for your business", title: "One platform, many trades", lead: "From a corner store to a multi-warehouse distributor \u2014 InvoiceSolution adapts to how you work." })), _jsx("div", { className: "grid gap-5 sm:grid-cols-2 lg:grid-cols-3", children: INDUSTRIES.map((ind, i) => (_jsx(Reveal, { delay: (i % 3) * 0.07, children: _jsxs(Link, { to: `/industries#${ind.id}`, className: "group flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-6 shadow-card transition-all hover:-translate-y-1 hover:border-brand-200 hover:shadow-glow", children: [_jsx("div", { className: "mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100", children: _jsx(Icon, { name: ind.icon, className: "h-5 w-5" }) }), _jsx("h3", { className: "text-lg font-semibold text-ink", children: ind.name }), _jsx("p", { className: "mt-1.5 flex-1 text-sm leading-relaxed text-ink-muted", children: ind.headline }), _jsxs("span", { className: "mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700 group-hover:gap-2.5", children: ["Explore ", _jsx(ArrowRight, { className: "h-4 w-4 transition-all" })] })] }) }, ind.id))) })] }));
}
