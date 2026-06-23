import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { BadgeCheck, Clock, QrCode, ShieldCheck } from "lucide-react";
const ITEMS = [
    { icon: BadgeCheck, label: "Real FBR invoice numbers" },
    { icon: QrCode, label: "Scannable QR receipts" },
    { icon: ShieldCheck, label: "6-year audit trail" },
    { icon: Clock, label: "72-hour edit window" },
];
/** Slim trust bar directly under the hero — compliance signals at a glance. */
export function TrustStrip() {
    return (_jsx("div", { className: "border-y border-slate-100 bg-slate-50/60", children: _jsx("div", { className: "container grid grid-cols-2 gap-4 py-6 sm:grid-cols-4", children: ITEMS.map(({ icon: Icon, label }) => (_jsxs("div", { className: "flex items-center justify-center gap-2.5 text-center", children: [_jsx(Icon, { className: "h-5 w-5 shrink-0 text-brand-600" }), _jsx("span", { className: "text-sm font-medium text-ink-soft", children: label })] }, label))) }) }));
}
