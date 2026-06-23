import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { SITE, whatsappLink } from "@/lib/site";
const COLUMNS = [
    {
        title: "Product",
        links: [
            { to: "/products", label: "POS Terminal" },
            { to: "/products#digital-invoicing", label: "Digital Invoicing" },
            { to: "/features", label: "Features" },
            { to: "/pricing", label: "Pricing" },
        ],
    },
    {
        title: "Solutions",
        links: [
            { to: "/industries#retail", label: "Retail & Grocery" },
            { to: "/industries#pharmacy", label: "Pharmacy" },
            { to: "/industries#restaurant", label: "Restaurant" },
            { to: "/industries#wholesale", label: "Wholesale & Distribution" },
        ],
    },
    {
        title: "Company",
        links: [
            { to: "/about", label: "About us" },
            { to: "/support", label: "Support" },
            { to: "/contact", label: "Contact" },
            { to: "/privacy", label: "Privacy Policy" },
            { to: "/terms", label: "Terms of Service" },
        ],
    },
];
export function Footer() {
    const year = new Date().getFullYear();
    return (_jsx("footer", { className: "border-t border-slate-200 bg-slate-50", children: _jsxs("div", { className: "container py-14", children: [_jsxs("div", { className: "grid gap-10 lg:grid-cols-[1.4fr_1fr_1fr_1fr]", children: [_jsxs("div", { children: [_jsx(Logo, {}), _jsx("p", { className: "mt-4 max-w-xs text-sm leading-relaxed text-ink-muted", children: "FBR-compliant Point of Sale & Digital Invoicing, built for Pakistani businesses. Real FBR invoice numbers, scannable QR, and software that keeps working even when your internet doesn\u2019t." }), _jsxs("div", { className: "mt-5 space-y-2 text-sm text-ink-soft", children: [_jsxs("a", { href: whatsappLink("Hi! I'd like to know more about InvoiceSolution."), target: "_blank", rel: "noopener noreferrer", className: "flex items-center gap-2 hover:text-brand-700", children: [_jsx(MessageCircle, { className: "h-4 w-4 text-brand-600" }), " WhatsApp us"] }), _jsxs("a", { href: `tel:${SITE.phoneTel}`, className: "flex items-center gap-2 hover:text-brand-700", children: [_jsx(Phone, { className: "h-4 w-4 text-brand-600" }), " ", SITE.phoneDisplay] }), _jsxs("a", { href: `mailto:${SITE.email}`, className: "flex items-center gap-2 hover:text-brand-700", children: [_jsx(Mail, { className: "h-4 w-4 text-brand-600" }), " ", SITE.email] }), _jsxs("span", { className: "flex items-center gap-2", children: [_jsx(MapPin, { className: "h-4 w-4 text-brand-600" }), " ", SITE.city] })] })] }), COLUMNS.map((col) => (_jsxs("div", { children: [_jsx("h3", { className: "text-sm font-semibold text-ink", children: col.title }), _jsx("ul", { className: "mt-4 space-y-2.5", children: col.links.map((l) => (_jsx("li", { children: _jsx(Link, { to: l.to, className: "text-sm text-ink-muted transition-colors hover:text-brand-700", children: l.label }) }, l.to + l.label))) })] }, col.title)))] }), _jsxs("div", { className: "mt-12 flex flex-col items-start justify-between gap-4 border-t border-slate-200 pt-6 text-sm text-ink-muted sm:flex-row sm:items-center", children: [_jsxs("p", { children: ["\u00A9 ", year, " ", SITE.name, ". All rights reserved."] }), _jsx("p", { className: "max-w-md text-xs leading-relaxed", children: "InvoiceSolution integrates with FBR Digital Invoicing via a PRAL-licensed integrator. We are an independent software provider and not a government body." })] })] }) }));
}
