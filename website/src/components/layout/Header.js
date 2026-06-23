import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AnimatePresence, motion } from "framer-motion";
import { LogIn, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";
import { Logo } from "@/components/layout/Logo";
import { cn } from "@/lib/cn";
import { SITE } from "@/lib/site";
const NAV = [
    { to: "/products", label: "Products" },
    { to: "/features", label: "Features" },
    { to: "/pricing", label: "Pricing" },
    { to: "/industries", label: "Industries" },
    { to: "/support", label: "Support" },
];
export function Header() {
    const [scrolled, setScrolled] = useState(false);
    const [open, setOpen] = useState(false);
    const location = useLocation();
    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 8);
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => window.removeEventListener("scroll", onScroll);
    }, []);
    // Close the mobile drawer on route change.
    useEffect(() => setOpen(false), [location.pathname]);
    // Lock body scroll while the drawer is open.
    useEffect(() => {
        document.body.style.overflow = open ? "hidden" : "";
        return () => {
            document.body.style.overflow = "";
        };
    }, [open]);
    return (_jsxs("header", { className: cn("sticky top-0 z-50 w-full transition-all duration-200", scrolled
            ? "border-b border-slate-200/70 bg-white/85 backdrop-blur-md shadow-soft"
            : "border-b border-transparent bg-white/0"), children: [_jsxs("div", { className: "container flex h-16 items-center justify-between gap-4", children: [_jsx(Logo, {}), _jsx("nav", { className: "hidden items-center gap-1 lg:flex", children: NAV.map((n) => (_jsx(NavLink, { to: n.to, className: ({ isActive }) => cn("rounded-lg px-3.5 py-2 text-sm font-medium transition-colors", isActive ? "text-brand-700" : "text-ink-soft hover:text-ink"), children: n.label }, n.to))) }), _jsxs("div", { className: "hidden items-center gap-2 lg:flex", children: [_jsxs(ButtonAnchor, { href: SITE.appUrl, variant: "ghost", size: "md", children: [_jsx(LogIn, { className: "h-4 w-4" }), " Login"] }), _jsx(ButtonLink, { to: "/contact", variant: "primary", size: "md", children: "Book a demo" })] }), _jsx("button", { type: "button", "aria-label": "Open menu", "aria-expanded": open, className: "inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink hover:bg-slate-100 lg:hidden", onClick: () => setOpen((v) => !v), children: open ? _jsx(X, { className: "h-5 w-5" }) : _jsx(Menu, { className: "h-5 w-5" }) })] }), _jsx(AnimatePresence, { children: open && (_jsx(motion.div, { className: "lg:hidden", initial: { opacity: 0, height: 0 }, animate: { opacity: 1, height: "auto" }, exit: { opacity: 0, height: 0 }, transition: { duration: 0.22, ease: "easeInOut" }, children: _jsxs("div", { className: "container space-y-1 border-t border-slate-100 bg-white pb-6 pt-3", children: [NAV.map((n) => (_jsx(NavLink, { to: n.to, className: ({ isActive }) => cn("block rounded-lg px-3 py-3 text-base font-medium", isActive ? "bg-brand-50 text-brand-700" : "text-ink hover:bg-slate-50"), children: n.label }, n.to))), _jsxs("div", { className: "grid grid-cols-2 gap-2 pt-3", children: [_jsxs(ButtonAnchor, { href: SITE.appUrl, variant: "secondary", size: "md", className: "w-full", children: [_jsx(LogIn, { className: "h-4 w-4" }), " Login"] }), _jsx(Link, { to: "/contact", className: "inline-flex h-11 w-full items-center justify-center rounded-lg bg-brand-600 px-5 text-sm font-semibold text-white", children: "Book a demo" })] })] }) })) })] }));
}
