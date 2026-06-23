import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { BookOpen, LogIn, Mail, MessageCircle, Phone, Rocket } from "lucide-react";
import { PageHero } from "@/components/sections/PageHero";
import { Accordion } from "@/components/ui/Accordion";
import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { FAQS } from "@/data/faqs";
import { SITE, whatsappLink } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";
const CHANNELS = [
    {
        icon: MessageCircle,
        title: "WhatsApp",
        desc: "The fastest way to reach us during business hours.",
        action: { label: "Chat on WhatsApp", href: whatsappLink("Hi! I need help with InvoiceSolution.") },
    },
    {
        icon: Phone,
        title: "Call us",
        desc: SITE.phoneDisplay,
        action: { label: "Call now", href: `tel:${SITE.phoneTel}` },
    },
    {
        icon: Mail,
        title: "Email",
        desc: SITE.email,
        action: { label: "Send an email", href: `mailto:${SITE.email}` },
    },
];
const STEPS = [
    { icon: MessageCircle, t: "Get in touch", d: "Book a demo or message us on WhatsApp. Tell us about your business." },
    { icon: Rocket, t: "We set you up", d: "Our team configures your FBR details, imports your products and creates your account." },
    { icon: BookOpen, t: "Quick training", d: "We train your staff on the till and the dashboard — usually under an hour." },
    { icon: LogIn, t: "Go live", d: "Start selling with FBR-validated invoices. We're a message away whenever you need us." },
];
export default function Support() {
    useSeo({
        title: "Support — We're here to help",
        description: "Get help with InvoiceSolution: FAQs, WhatsApp, phone and email support, and a simple guided onboarding process.",
        path: "/support",
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Support", title: "Help, whenever you need it", lead: "Real people who know FBR and know retail. Reach us on WhatsApp, phone or email \u2014 or find a quick answer below." }), _jsx("section", { className: "container -mt-6 pb-8", children: _jsx("div", { className: "grid gap-5 md:grid-cols-3", children: CHANNELS.map((c, i) => (_jsx(Reveal, { delay: i * 0.07, children: _jsxs("div", { className: "flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-7 text-center shadow-card", children: [_jsx("span", { className: "mx-auto mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600", children: _jsx(c.icon, { className: "h-6 w-6" }) }), _jsx("h3", { className: "text-lg font-semibold text-ink", children: c.title }), _jsx("p", { className: "mt-1 flex-1 text-sm text-ink-muted", children: c.desc }), _jsx(ButtonAnchor, { href: c.action.href, variant: "secondary", className: "mt-5", children: c.action.label })] }) }, c.title))) }) }), _jsx("section", { className: "bg-slate-50/60", children: _jsxs("div", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "Getting started", title: "From sign-up to selling in days", lead: "Onboarding is guided \u2014 you're never left to figure out FBR on your own." }), _jsx("div", { className: "grid gap-6 md:grid-cols-4", children: STEPS.map((s, i) => (_jsx(Reveal, { delay: i * 0.08, children: _jsxs("div", { className: "relative h-full rounded-2xl border border-slate-100 bg-white p-6 shadow-soft", children: [_jsxs("div", { className: "mb-3 text-sm font-bold text-brand-600", children: ["Step ", i + 1] }), _jsx(s.icon, { className: "h-6 w-6 text-brand-600" }), _jsx("h3", { className: "mt-3 font-semibold text-ink", children: s.t }), _jsx("p", { className: "mt-1.5 text-sm text-ink-muted", children: s.d })] }) }, s.t))) })] }) }), _jsxs("section", { className: "container section", children: [_jsx(SectionHeading, { eyebrow: "FAQ", title: "Frequently asked questions", center: true }), _jsx("div", { className: "mx-auto max-w-3xl", children: _jsx(Accordion, { items: FAQS }) }), _jsxs("div", { className: "mx-auto mt-10 max-w-xl rounded-2xl border border-slate-100 bg-white p-7 text-center shadow-soft", children: [_jsx("h3", { className: "text-lg font-semibold text-ink", children: "Still have a question?" }), _jsx("p", { className: "mt-1.5 text-sm text-ink-muted", children: "Our team replies fast. Book a demo or message us and we\u2019ll help you get set up." }), _jsxs("div", { className: "mt-5 flex flex-wrap justify-center gap-3", children: [_jsx(ButtonLink, { to: "/contact", children: "Contact us" }), _jsxs(ButtonAnchor, { href: SITE.appUrl, variant: "secondary", children: [_jsx(LogIn, { className: "h-4 w-4" }), " Existing customer login"] })] })] })] })] }));
}
