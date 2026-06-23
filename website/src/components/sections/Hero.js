import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, BadgeCheck, ShieldCheck, WifiOff } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { ReceiptMock } from "@/components/sections/ReceiptMock";
import { cn } from "@/lib/cn";
export function Hero() {
    const reduce = useReducedMotion();
    const rise = (delay) => reduce
        ? {}
        : {
            initial: { opacity: 0, y: 20 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] },
        };
    return (_jsxs("section", { className: "relative overflow-hidden", children: [_jsx("div", { "aria-hidden": true, className: "absolute inset-0 -z-10 mesh" }), _jsx("div", { "aria-hidden": true, className: "absolute inset-0 -z-10 bg-grid-faint bg-[size:44px_44px] [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]" }), _jsxs("div", { className: "container grid items-center gap-14 pb-16 pt-14 sm:pt-20 lg:grid-cols-2 lg:gap-8 lg:pb-24 lg:pt-24", children: [_jsxs("div", { children: [_jsx(motion.div, { ...rise(0), children: _jsxs("span", { className: "eyebrow", children: [_jsx(BadgeCheck, { className: "h-3.5 w-3.5" }), " FBR Digital Invoicing"] }) }), _jsxs(motion.h1, { ...rise(0.06), className: "h1 mt-5", children: ["Run your shop.", " ", _jsx("span", { className: "relative whitespace-nowrap text-brand-600", children: "Stay FBR-compliant." }), " ", "Even offline."] }), _jsx(motion.p, { ...rise(0.12), className: "lead mt-5 max-w-xl", children: "InvoiceSolution is the FBR-compliant POS & Digital Invoicing system built for Pakistani businesses. Real FBR invoice numbers, scannable QR receipts, and software that keeps selling when your internet doesn\u2019t." }), _jsxs(motion.div, { ...rise(0.18), className: "mt-8 flex flex-wrap items-center gap-3", children: [_jsxs(ButtonLink, { to: "/contact", size: "lg", children: ["Book a free demo ", _jsx(ArrowRight, { className: "h-4 w-4" })] }), _jsx(ButtonLink, { to: "/pricing", variant: "secondary", size: "lg", children: "See pricing" })] }), _jsxs(motion.div, { ...rise(0.26), className: "mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-muted", children: [_jsxs("span", { className: "flex items-center gap-2", children: [_jsx(ShieldCheck, { className: "h-4 w-4 text-brand-600" }), " Real FBR invoice numbers"] }), _jsxs("span", { className: "flex items-center gap-2", children: [_jsx(WifiOff, { className: "h-4 w-4 text-brand-600" }), " Works offline"] }), _jsxs("span", { className: "flex items-center gap-2", children: [_jsx(BadgeCheck, { className: "h-4 w-4 text-brand-600" }), " 14-day trial"] })] })] }), _jsxs(motion.div, { ...(reduce
                            ? {}
                            : {
                                initial: { opacity: 0, scale: 0.96, y: 24 },
                                animate: { opacity: 1, scale: 1, y: 0 },
                                transition: { duration: 0.7, delay: 0.15, ease: [0.22, 1, 0.36, 1] },
                            }), className: "relative mx-auto w-full max-w-md lg:max-w-none", children: [_jsx("div", { className: cn("relative", !reduce && "animate-float"), children: _jsx(ReceiptMock, {}) }), _jsxs(FloatChip, { className: "-left-2 top-8 sm:-left-6", delay: 0.5, reduce: reduce, children: [_jsx("span", { className: "text-xs font-medium text-ink-muted", children: "Today\u2019s sales" }), _jsx("span", { className: "text-lg font-bold text-ink", children: "Rs 84,250.00" })] }), _jsx(FloatChip, { className: "-right-2 bottom-10 sm:-right-6", delay: 0.7, reduce: reduce, children: _jsxs("div", { className: "flex items-center gap-2", children: [_jsxs("span", { className: "relative flex h-2.5 w-2.5", children: [_jsx("span", { className: "absolute inline-flex h-full w-full animate-pulse-dot rounded-full bg-brand-500" }), _jsx("span", { className: "relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-600" })] }), _jsx("span", { className: "text-xs font-medium text-ink", children: "Synced to FBR" })] }) })] })] })] }));
}
function FloatChip({ children, className, delay, reduce, }) {
    return (_jsx(motion.div, { ...(reduce
            ? {}
            : {
                initial: { opacity: 0, y: 12 },
                animate: { opacity: 1, y: 0 },
                transition: { duration: 0.5, delay },
            }), className: cn("absolute flex flex-col gap-0.5 rounded-xl border border-slate-100 bg-white/95 px-4 py-3 shadow-card backdrop-blur", className), children: children }));
}
