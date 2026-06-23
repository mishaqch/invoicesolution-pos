import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";
/** Single-open FAQ accordion with animated expand/collapse. */
export function Accordion({ items }) {
    const [open, setOpen] = useState(0);
    return (_jsx("div", { className: "divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white shadow-soft", children: items.map((item, i) => {
            const isOpen = open === i;
            return (_jsxs("div", { children: [_jsxs("button", { type: "button", onClick: () => setOpen(isOpen ? null : i), "aria-expanded": isOpen, className: "flex w-full items-center justify-between gap-4 px-5 py-5 text-left sm:px-6", children: [_jsx("span", { className: "font-semibold text-ink", children: item.q }), _jsx(ChevronDown, { className: cn("h-5 w-5 shrink-0 text-brand-600 transition-transform duration-200", isOpen && "rotate-180") })] }), _jsx(AnimatePresence, { initial: false, children: isOpen && (_jsx(motion.div, { initial: { height: 0, opacity: 0 }, animate: { height: "auto", opacity: 1 }, exit: { height: 0, opacity: 0 }, transition: { duration: 0.25, ease: "easeInOut" }, className: "overflow-hidden", children: _jsx("p", { className: "px-5 pb-5 text-ink-soft sm:px-6", children: item.a }) })) })] }, i));
        }) }));
}
