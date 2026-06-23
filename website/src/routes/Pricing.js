import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Check, Minus } from "lucide-react";
import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { PricingCards } from "@/components/sections/PricingCards";
import { Accordion } from "@/components/ui/Accordion";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { COMPARISON, PLANS } from "@/data/plans";
import { useSeo } from "@/lib/useSeo";
const PRICING_FAQ = [
    { q: "Is there a free trial?", a: "Yes — new accounts include a 14-day trial so you can see InvoiceSolution working with your own products before you commit." },
    { q: "How do I pay for my subscription?", a: "You can pay by bank transfer, JazzCash Business, EasyPaisa Business or Raast. Our team shares the details during onboarding." },
    { q: "Can I change plans later?", a: "Absolutely. Start on Starter and move up to Pro or Enterprise as you add branches, terminals or team members — just let us know." },
    { q: "Do prices include FBR fees?", a: "Our subscription covers the InvoiceSolution software and FBR Digital Invoicing integration. Any fees charged directly by FBR/PRAL to your business are separate." },
];
function rs(n) {
    return n.toLocaleString("en-PK");
}
export default function Pricing() {
    useSeo({
        title: "Pricing — Simple plans in PKR",
        description: "Transparent pricing for InvoiceSolution: Starter Rs 2,000/mo, Pro Rs 5,000/mo, Enterprise Rs 15,000/mo. All plans fully FBR-compliant. 14-day trial.",
        path: "/pricing",
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Pricing", title: "Simple, transparent pricing", lead: "Every plan is fully FBR-compliant and offline-first. Pay monthly or save with yearly. All prices in PKR." }), _jsx("section", { className: "container pb-8", children: _jsx(PricingCards, {}) }), _jsx("section", { className: "bg-slate-50/60", children: _jsxs("div", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Compare", title: "Everything in each plan", center: true }), _jsx(Reveal, { children: _jsx("div", { className: "overflow-x-auto rounded-2xl border border-slate-100 bg-white shadow-soft", children: _jsxs("table", { className: "w-full min-w-[640px] text-sm", children: [_jsx("thead", { children: _jsxs("tr", { className: "border-b border-slate-100", children: [_jsx("th", { className: "px-5 py-4 text-left font-semibold text-ink", children: "Feature" }), PLANS.map((p) => (_jsxs("th", { className: "px-5 py-4 text-center font-semibold text-ink", children: [_jsx("div", { children: p.name }), _jsxs("div", { className: "text-xs font-normal text-ink-muted", children: ["Rs ", rs(p.monthly), "/mo"] })] }, p.name)))] }) }), _jsx("tbody", { children: COMPARISON.map((row, i) => (_jsxs("tr", { className: i % 2 ? "bg-slate-50/50" : undefined, children: [_jsx("td", { className: "px-5 py-3 text-ink-soft", children: row.label }), row.values.map((v, j) => (_jsx("td", { className: "px-5 py-3 text-center", children: v === "✓" ? (_jsx(Check, { className: "mx-auto h-4 w-4 text-brand-600" })) : v === "—" ? (_jsx(Minus, { className: "mx-auto h-4 w-4 text-slate-300" })) : (_jsx("span", { className: "font-medium text-ink", children: v })) }, j)))] }, row.label))) })] }) }) })] }) }), _jsxs("section", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Questions", title: "Pricing FAQ", center: true }), _jsx("div", { className: "mx-auto max-w-3xl", children: _jsx(Accordion, { items: PRICING_FAQ }) })] }), _jsx(CtaBand, { title: "Try it with your own products", subtitle: "Start your 14-day trial \u2014 we'll set everything up and walk you through it." })] }));
}
