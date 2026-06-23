import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Check } from "lucide-react";
import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { ButtonLink } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
import { INDUSTRIES } from "@/data/industries";
import { useSeo } from "@/lib/useSeo";
export default function Industries() {
    useSeo({
        title: "Industries — Built for your trade",
        description: "Retail, pharmacy, restaurant, wholesale, service providers and importers/exporters — InvoiceSolution adapts to how your business works.",
        path: "/industries",
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Industries", title: "Shaped to fit how you work", lead: "One FBR-compliant platform, tuned for the realities of each trade \u2014 from a corner store to a multi-warehouse distributor.", children: _jsx(ButtonLink, { to: "/contact", size: "lg", children: "Book a demo" }) }), INDUSTRIES.map((ind, i) => (_jsx("section", { id: ind.id, className: `scroll-mt-20 ${i % 2 === 1 ? "bg-slate-50/60" : ""}`, children: _jsx("div", { className: "container section", children: _jsxs("div", { className: "grid items-center gap-10 lg:grid-cols-2", children: [_jsxs(Reveal, { className: i % 2 === 1 ? "lg:order-2" : "", children: [_jsx("div", { className: "mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100", children: _jsx(Icon, { name: ind.icon, className: "h-6 w-6" }) }), _jsx("span", { className: "eyebrow", children: ind.name }), _jsx("h2", { className: "h2 mt-3", children: ind.headline }), _jsx("p", { className: "lead mt-4", children: ind.desc }), _jsxs(ButtonLink, { to: "/contact", className: "mt-7", children: ["Talk to us about ", ind.name.toLowerCase()] })] }), _jsx(Reveal, { delay: 0.1, className: i % 2 === 1 ? "lg:order-1" : "", children: _jsx("div", { className: "grid gap-3 sm:grid-cols-2", children: ind.points.map((pt) => (_jsxs("div", { className: "flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-4 shadow-soft", children: [_jsx("span", { className: "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50", children: _jsx(Check, { className: "h-4 w-4 text-brand-600" }) }), _jsx("span", { className: "text-sm font-medium text-ink", children: pt })] }, pt))) }) })] }) }) }, ind.id))), _jsx(CtaBand, {})] }));
}
