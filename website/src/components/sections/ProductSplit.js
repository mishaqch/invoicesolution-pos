import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { ArrowRight, Monitor, ScanLine, Store, WifiOff } from "lucide-react";
import { FileText, Layers, Send, Warehouse } from "lucide-react";
import { Link } from "react-router-dom";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { cn } from "@/lib/cn";
const PRODUCTS = [
    {
        tag: "POS Terminal",
        title: "For shops with a counter",
        desc: "A fast, offline-first cashier system for retailers, pharmacies and restaurants. Scan, sell, print FBR receipts — even during outages.",
        to: "/products#pos",
        accent: "from-brand-600 to-emerald-500",
        points: [
            { icon: WifiOff, label: "Works fully offline" },
            { icon: ScanLine, label: "Barcode & thermal printing" },
            { icon: Monitor, label: "Customer-facing display" },
            { icon: Store, label: "Multi-branch & multi-till" },
        ],
    },
    {
        tag: "Digital Invoicing",
        title: "For back-office invoicing",
        desc: "Issue FBR-compliant invoices from your browser — no till, no hardware. Ideal for wholesalers, distributors and service providers.",
        to: "/products#digital-invoicing",
        accent: "from-slate-800 to-slate-600",
        points: [
            { icon: FileText, label: "No hardware needed" },
            { icon: Warehouse, label: "Multi-warehouse stock" },
            { icon: Layers, label: "High invoice volumes" },
            { icon: Send, label: "Direct FBR submission" },
        ],
    },
];
export function ProductSplit() {
    return (_jsxs("div", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Two products, one platform", title: "Pick the way you invoice", lead: "Whether you sell over a counter or raise invoices from the office, there's a product shaped for you \u2014 both fully FBR-compliant." }), _jsx("div", { className: "grid gap-6 lg:grid-cols-2", children: PRODUCTS.map((p, i) => (_jsx(Reveal, { delay: i * 0.08, children: _jsxs("div", { className: "group relative h-full overflow-hidden rounded-2xl border border-slate-100 bg-white p-7 shadow-card transition-all hover:-translate-y-1 hover:shadow-glow", children: [_jsx("div", { className: cn("inline-flex rounded-full bg-gradient-to-r px-3 py-1 text-xs font-semibold text-white", p.accent), children: p.tag }), _jsx("h3", { className: "h3 mt-4", children: p.title }), _jsx("p", { className: "mt-2 text-ink-soft", children: p.desc }), _jsx("ul", { className: "mt-6 grid grid-cols-2 gap-3", children: p.points.map(({ icon: Icon, label }) => (_jsxs("li", { className: "flex items-center gap-2 text-sm text-ink-soft", children: [_jsx(Icon, { className: "h-4 w-4 shrink-0 text-brand-600" }), " ", label] }, label))) }), _jsxs(Link, { to: p.to, className: "mt-7 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700 hover:gap-2.5", children: ["Learn more ", _jsx(ArrowRight, { className: "h-4 w-4 transition-all" })] })] }) }, p.tag))) })] }));
}
