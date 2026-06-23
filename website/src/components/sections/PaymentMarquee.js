import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Banknote, Building2, CreditCard, ReceiptText, Smartphone, Wallet, Zap } from "lucide-react";
import { Marquee } from "@/components/ui/Marquee";
const METHODS = [
    { icon: Banknote, label: "Cash" },
    { icon: CreditCard, label: "Card" },
    { icon: Smartphone, label: "EasyPaisa" },
    { icon: Smartphone, label: "JazzCash" },
    { icon: Zap, label: "Raast" },
    { icon: Building2, label: "Bank transfer" },
    { icon: ReceiptText, label: "Cheque" },
    { icon: Wallet, label: "Store credit" },
];
/** Scrolling strip of accepted payment methods. */
export function PaymentMarquee() {
    return (_jsxs("div", { className: "container section", children: [_jsxs("div", { className: "mx-auto mb-10 max-w-xl text-center", children: [_jsx("span", { className: "eyebrow", children: "Payments" }), _jsx("h2", { className: "h2 mt-4", children: "Accept every way Pakistan pays" }), _jsx("p", { className: "lead mt-3", children: "Cash to Raast, wallets to cheques \u2014 record it all on one invoice, including split and credit sales." })] }), _jsx(Marquee, { children: METHODS.map((m) => (_jsxs("div", { className: "flex items-center gap-2.5 rounded-xl border border-slate-100 bg-white px-5 py-3 shadow-soft", children: [_jsx(m.icon, { className: "h-5 w-5 text-brand-600" }), _jsx("span", { className: "whitespace-nowrap text-sm font-semibold text-ink", children: m.label })] }, m.label))) })] }));
}
