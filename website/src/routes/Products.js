import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Boxes, Check, CreditCard, FileText, Monitor, Printer, ScanLine, Send, ShieldCheck, Store, Warehouse, WifiOff, } from "lucide-react";
import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { ReceiptMock } from "@/components/sections/ReceiptMock";
import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { useSeo } from "@/lib/useSeo";
const POS_POINTS = [
    { icon: WifiOff, t: "Offline-first", d: "Keep selling through power cuts and internet outages; auto-syncs when back online." },
    { icon: ScanLine, t: "Barcode checkout", d: "Plug-and-play USB scanners with no drivers — just scan and sell." },
    { icon: Printer, t: "Thermal receipts", d: "58mm and 80mm ESC/POS printers with FBR logo and scannable QR." },
    { icon: Monitor, t: "Customer display", d: "Show items and the running total on a second screen for the customer." },
    { icon: CreditCard, t: "All payment methods", d: "Cash, card, wallets, Raast, cheque, bank, store credit — and split payments." },
    { icon: Store, t: "Multi-branch & multi-till", d: "Run several terminals per shop, all syncing to one central account." },
];
const DI_POINTS = [
    { icon: FileText, t: "No hardware needed", d: "Raise FBR-compliant invoices straight from your browser — no till required." },
    { icon: Warehouse, t: "Multi-warehouse stock", d: "Track on-hand across warehouses with transfers and audits." },
    { icon: Send, t: "Direct FBR submission", d: "Validate and submit to FBR Digital Invoicing, with real invoice numbers and QR." },
    { icon: Boxes, t: "High invoice volumes", d: "Built for wholesalers and distributors issuing many invoices a day." },
    { icon: ShieldCheck, t: "Edit & cancel rules", d: "72-hour edit window and monthly cancel limits enforced exactly per FBR." },
];
export default function Products() {
    useSeo({
        title: "Products — POS Terminal & Digital Invoicing",
        description: "Two FBR-compliant products: an offline-first POS Terminal for counter-side shops, and Digital Invoicing for back-office invoicing without hardware.",
        path: "/products",
    });
    return (_jsxs(_Fragment, { children: [_jsxs(PageHero, { eyebrow: "Products", title: "Two ways to invoice, both 100% FBR-compliant", lead: "A counter-side POS for shops, and back-office Digital Invoicing for everyone else. Use one \u2014 or both.", children: [_jsx(ButtonLink, { to: "/contact", size: "lg", children: "Book a demo" }), _jsx(ButtonLink, { to: "/pricing", variant: "secondary", size: "lg", children: "See pricing" })] }), _jsx("section", { id: "pos", className: "container section scroll-mt-20", children: _jsxs("div", { className: "grid items-center gap-12 lg:grid-cols-2", children: [_jsxs(Reveal, { children: [_jsx("span", { className: "eyebrow", children: "POS Terminal" }), _jsx("h2", { className: "h2 mt-4", children: "The fastest FBR-ready counter in Pakistan" }), _jsx("p", { className: "lead mt-4", children: "Scan, ring up, take any payment and print an FBR receipt in seconds. The terminal runs on affordable Windows hardware and keeps working when your connection doesn\u2019t." }), _jsx("div", { className: "mt-8 grid gap-5 sm:grid-cols-2", children: POS_POINTS.map((p) => (_jsxs("div", { className: "flex gap-3", children: [_jsx(p.icon, { className: "mt-0.5 h-5 w-5 shrink-0 text-brand-600" }), _jsxs("div", { children: [_jsx("div", { className: "font-semibold text-ink", children: p.t }), _jsx("div", { className: "text-sm text-ink-muted", children: p.d })] })] }, p.t))) })] }), _jsx(Reveal, { delay: 0.1, children: _jsx(ReceiptMock, {}) })] }) }), _jsx("section", { id: "digital-invoicing", className: "scroll-mt-20 bg-slate-50/60", children: _jsx("div", { className: "container section", children: _jsxs("div", { className: "grid items-center gap-12 lg:grid-cols-2", children: [_jsxs(Reveal, { className: "lg:order-2", children: [_jsx("span", { className: "eyebrow", children: "Digital Invoicing" }), _jsx("h2", { className: "h2 mt-4", children: "FBR invoices from your browser" }), _jsx("p", { className: "lead mt-4", children: "For wholesalers, distributors, importers and service providers who invoice from the office. No printer, no scanner, no till \u2014 just compliant invoices, fast." }), _jsx("div", { className: "mt-8 grid gap-5 sm:grid-cols-2", children: DI_POINTS.map((p) => (_jsxs("div", { className: "flex gap-3", children: [_jsx(p.icon, { className: "mt-0.5 h-5 w-5 shrink-0 text-brand-600" }), _jsxs("div", { children: [_jsx("div", { className: "font-semibold text-ink", children: p.t }), _jsx("div", { className: "text-sm text-ink-muted", children: p.d })] })] }, p.t))) })] }), _jsx(Reveal, { delay: 0.1, className: "lg:order-1", children: _jsx(DiMock, {}) })] }) }) }), _jsxs("section", { className: "container section", children: [_jsxs("div", { className: "mx-auto max-w-2xl text-center", children: [_jsx("span", { className: "eyebrow", children: "Not sure which?" }), _jsx("h2", { className: "h2 mt-4", children: "Which product is right for me?" })] }), _jsxs("div", { className: "mt-10 grid gap-6 lg:grid-cols-2", children: [_jsx(Reveal, { children: _jsx(ChooseCard, { title: "Choose POS Terminal if\u2026", items: [
                                        "You sell over a counter with a till",
                                        "You need barcode scanning & thermal receipts",
                                        "You're a retailer, pharmacy or restaurant",
                                        "You want to keep selling during outages",
                                    ] }) }), _jsx(Reveal, { delay: 0.08, children: _jsx(ChooseCard, { title: "Choose Digital Invoicing if\u2026", items: [
                                        "You invoice from a back office, not a counter",
                                        "You're a wholesaler, distributor or service provider",
                                        "You don't need printers or scanners",
                                        "You issue many invoices across warehouses",
                                    ] }) })] }), _jsx("p", { className: "mt-8 text-center text-sm text-ink-muted", children: "Need both? Many businesses run the POS and Digital Invoicing together \u2014 we\u2019ll set up the right mix for you." })] }), _jsx(CtaBand, {})] }));
}
function ChooseCard({ title, items }) {
    return (_jsxs("div", { className: "h-full rounded-2xl border border-slate-100 bg-white p-7 shadow-card", children: [_jsx("h3", { className: "text-lg font-semibold text-ink", children: title }), _jsx("ul", { className: "mt-5 space-y-3", children: items.map((it) => (_jsxs("li", { className: "flex items-start gap-2.5 text-ink-soft", children: [_jsx(Check, { className: "mt-0.5 h-4 w-4 shrink-0 text-brand-600" }), " ", it] }, it))) })] }));
}
/** Simple dashboard-style mock for the Digital Invoicing section. */
function DiMock() {
    return (_jsxs("div", { className: "rounded-2xl border border-slate-100 bg-white p-4 shadow-card", children: [_jsxs("div", { className: "mb-3 flex items-center justify-between", children: [_jsx("span", { className: "text-sm font-semibold text-ink", children: "Invoices" }), _jsx("span", { className: "rounded-lg bg-brand-600 px-3 py-1 text-xs font-semibold text-white", children: "+ New invoice" })] }), _jsx("div", { className: "overflow-hidden rounded-xl border border-slate-100", children: [
                    ["INV-2026-0481", "Al-Karam Traders", "Rs 128,400.00", "Valid"],
                    ["INV-2026-0480", "Hassan Distributors", "Rs 54,900.00", "Valid"],
                    ["INV-2026-0479", "Metro Wholesale", "Rs 312,750.00", "Valid"],
                    ["INV-2026-0478", "City Pharma", "Rs 18,250.00", "Pending"],
                ].map(([no, buyer, amt, status], i) => (_jsxs("div", { className: `grid grid-cols-[1fr_auto] items-center gap-2 px-4 py-3 text-[13px] ${i % 2 ? "bg-slate-50/60" : "bg-white"}`, children: [_jsxs("div", { children: [_jsx("div", { className: "font-mono text-xs text-ink-muted", children: no }), _jsx("div", { className: "font-medium text-ink", children: buyer })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "font-mono text-ink", children: amt }), _jsxs("span", { className: `text-[11px] font-semibold ${status === "Valid" ? "text-brand-700" : "text-amber-600"}`, children: [status === "Valid" ? "✓ " : "• ", status] })] })] }, no))) })] }));
}
