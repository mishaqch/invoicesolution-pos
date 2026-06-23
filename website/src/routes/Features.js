import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { CtaBand } from "@/components/sections/CtaBand";
import { FeatureGrid } from "@/components/sections/FeatureGrid";
import { PageHero } from "@/components/sections/PageHero";
import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { FEATURE_GROUPS } from "@/data/features";
import { useSeo } from "@/lib/useSeo";
export default function Features() {
    useSeo({
        title: "Features — Everything InvoiceSolution does",
        description: "FBR compliance, offline-first sales, every payment method, multi-branch inventory, reports, returns, roles and hardware — explore the full feature set.",
        path: "/features",
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Features", title: "A complete toolkit to run a compliant business", lead: "Everything from the first scan to the FBR-validated receipt \u2014 and every report, return and role in between.", children: _jsx(ButtonLink, { to: "/contact", size: "lg", children: "Book a demo" }) }), FEATURE_GROUPS.map((group, i) => (_jsx("section", { className: i % 2 === 1 ? "bg-slate-50/60" : undefined, children: _jsxs("div", { className: "container section", children: [_jsx(Reveal, { children: _jsxs("div", { className: "mb-10 max-w-2xl", children: [_jsx("span", { className: "eyebrow", children: group.category }), _jsx("p", { className: "lead mt-4", children: group.blurb })] }) }), _jsx(FeatureGrid, { features: group.features, columns: 3 })] }) }, group.category))), _jsx(CtaBand, {})] }));
}
