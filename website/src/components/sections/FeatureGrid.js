import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Card, IconChip } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
/** Responsive grid of feature cards. Used on Home and Features pages. */
export function FeatureGrid({ features, columns = 4 }) {
    const cols = columns === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4";
    return (_jsx("div", { className: `grid gap-5 sm:grid-cols-2 ${cols}`, children: features.map((f, i) => (_jsx(Reveal, { delay: (i % 4) * 0.06, children: _jsxs(Card, { className: "h-full", children: [_jsx(IconChip, { children: _jsx(Icon, { name: f.icon, className: "h-5 w-5" }) }), _jsx("h3", { className: "text-base font-semibold text-ink", children: f.title }), _jsx("p", { className: "mt-1.5 text-sm leading-relaxed text-ink-muted", children: f.desc })] }) }, f.title))) }));
}
