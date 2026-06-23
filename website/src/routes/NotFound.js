import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";
import { SITE } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";
export default function NotFound() {
    useSeo({ title: "Page not found", path: "/404" });
    return (_jsxs("section", { className: "relative overflow-hidden", children: [_jsx("div", { "aria-hidden": true, className: "absolute inset-0 -z-10 mesh" }), _jsxs("div", { className: "container flex min-h-[60vh] flex-col items-center justify-center py-24 text-center", children: [_jsx("div", { className: "text-7xl font-extrabold tracking-tight text-brand-600 sm:text-8xl", children: "404" }), _jsx("h1", { className: "mt-4 text-2xl font-bold text-ink sm:text-3xl", children: "This page wandered off" }), _jsx("p", { className: "mt-3 max-w-md text-ink-muted", children: "The page you\u2019re looking for doesn\u2019t exist or may have moved. Let\u2019s get you back on track." }), _jsxs("div", { className: "mt-7 flex flex-wrap items-center justify-center gap-3", children: [_jsx(ButtonLink, { to: "/", size: "lg", children: "Back to home" }), _jsx(ButtonAnchor, { href: SITE.appUrl, variant: "secondary", size: "lg", children: "Customer login" })] })] })] }));
}
