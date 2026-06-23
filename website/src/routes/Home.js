import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { CtaBand } from "@/components/sections/CtaBand";
import { FeatureGrid } from "@/components/sections/FeatureGrid";
import { Hero } from "@/components/sections/Hero";
import { IndustryCards } from "@/components/sections/IndustryCards";
import { OfflineStory } from "@/components/sections/OfflineStory";
import { PaymentMarquee } from "@/components/sections/PaymentMarquee";
import { PricingCards } from "@/components/sections/PricingCards";
import { ProductSplit } from "@/components/sections/ProductSplit";
import { Stats } from "@/components/sections/Stats";
import { TrustStrip } from "@/components/sections/TrustStrip";
import { SectionHeading } from "@/components/ui/Section";
import { HOME_FEATURES } from "@/data/features";
import { useSeo } from "@/lib/useSeo";
export default function Home() {
    useSeo({
        title: "InvoiceSolution — FBR-Compliant POS & Digital Invoicing for Pakistan",
        description: "FBR-compliant POS and Digital Invoicing for Pakistani businesses. Real FBR invoice numbers, scannable QR receipts, all payment methods, and software that works even offline.",
        path: "/",
    });
    return (_jsxs(_Fragment, { children: [_jsx(Hero, {}), _jsx(TrustStrip, {}), _jsx(ProductSplit, {}), _jsx("div", { className: "bg-slate-50/60", children: _jsxs("div", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Everything you need", title: "One system to run and report your business", lead: "From the first scan to the FBR-validated receipt \u2014 and every report in between." }), _jsx(FeatureGrid, { features: HOME_FEATURES, columns: 4 })] }) }), _jsx(OfflineStory, {}), _jsx(PaymentMarquee, {}), _jsx("div", { className: "py-12", children: _jsx(Stats, {}) }), _jsx(IndustryCards, {}), _jsx("div", { className: "bg-slate-50/60", children: _jsxs("div", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Simple, honest pricing", title: "Plans that grow with you", lead: "Start with a single shop and scale to unlimited branches. All plans are fully FBR-compliant." }), _jsx(PricingCards, { compact: true })] }) }), _jsx(CtaBand, {})] }));
}
