import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/** Compact hero band for inner pages (Products, Features, Pricing, …). */
export function PageHero({ eyebrow, title, lead, children, }) {
    return (_jsxs("section", { className: "relative overflow-hidden border-b border-slate-100", children: [_jsx("div", { "aria-hidden": true, className: "absolute inset-0 -z-10 mesh" }), _jsxs("div", { className: "container py-16 text-center sm:py-20", children: [eyebrow && _jsx("span", { className: "eyebrow mb-4", children: eyebrow }), _jsx("h1", { className: "mx-auto max-w-3xl text-4xl font-extrabold leading-[1.1] tracking-tight text-ink sm:text-5xl", children: title }), lead && _jsx("p", { className: "lead mx-auto mt-5 max-w-2xl", children: lead }), children && _jsx("div", { className: "mt-8 flex flex-wrap items-center justify-center gap-3", children: children })] })] }));
}
