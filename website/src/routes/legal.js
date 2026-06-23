import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { PageHero } from "@/components/sections/PageHero";
/** Shared shell + simple prose styling for legal pages. */
export function LegalLayout({ title, updated, children, }) {
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Legal", title: title, lead: `Last updated: ${updated}` }), _jsx("section", { className: "container section", children: _jsx("div", { className: "prose-legal mx-auto max-w-3xl space-y-6 text-ink-soft [&_h2]:mb-2 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-ink [&_p]:leading-relaxed [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5", children: children }) })] }));
}
