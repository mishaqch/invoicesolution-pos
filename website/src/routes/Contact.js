import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { CheckCircle2, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { useState } from "react";
import { PageHero } from "@/components/sections/PageHero";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { LeadError, submitLead } from "@/lib/api";
import { cn } from "@/lib/cn";
import { SITE, whatsappLink } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";
const BUSINESS_TYPES = [
    "Retail / Grocery",
    "Pharmacy",
    "Restaurant / Café",
    "Wholesale / Distribution",
    "Service provider",
    "Importer / Exporter",
    "Other",
];
const emptyForm = {
    name: "",
    business_name: "",
    phone: "",
    email: "",
    city: "",
    business_type: "",
    product_interest: "",
    message: "",
    company_website: "", // honeypot
};
export default function Contact() {
    useSeo({
        title: "Contact — Book a free demo",
        description: "Get in touch to book a free demo of InvoiceSolution. We'll set up your FBR-compliant POS or Digital Invoicing account and train your team.",
        path: "/contact",
    });
    const [form, setForm] = useState(emptyForm);
    const [errors, setErrors] = useState({});
    const [status, setStatus] = useState("idle");
    const [errorMsg, setErrorMsg] = useState("");
    function set(key, value) {
        setForm((f) => ({ ...f, [key]: value }));
    }
    function clientValidate() {
        const e = {};
        if (!form.name.trim())
            e.name = ["Please enter your name."];
        if (!form.business_name.trim())
            e.business_name = ["Please enter your business name."];
        if (!form.phone.trim())
            e.phone = ["Please enter a phone number."];
        else if (!/^[0-9+\-\s()]{7,}$/.test(form.phone))
            e.phone = ["Enter a valid phone number."];
        if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
            e.email = ["Enter a valid email."];
        if (!form.product_interest)
            e.product_interest = ["Please choose what you're interested in."];
        setErrors(e);
        return Object.keys(e).length === 0;
    }
    async function onSubmit(ev) {
        ev.preventDefault();
        setErrorMsg("");
        if (!clientValidate())
            return;
        setStatus("sending");
        try {
            await submitLead(form);
            setStatus("done");
            setForm(emptyForm);
        }
        catch (err) {
            if (err instanceof LeadError) {
                setErrorMsg(err.message);
                if (err.fields)
                    setErrors(err.fields);
            }
            else {
                setErrorMsg("Something went wrong. Please try again.");
            }
            setStatus("error");
        }
    }
    return (_jsxs(_Fragment, { children: [_jsx(PageHero, { eyebrow: "Contact", title: "Let's get your business FBR-ready", lead: "Tell us a little about your shop and we'll be in touch to book your demo and set everything up." }), _jsx("section", { className: "container pb-20", children: _jsxs("div", { className: "grid gap-10 lg:grid-cols-[1.3fr_1fr]", children: [_jsx(Reveal, { children: _jsx("div", { className: "rounded-2xl border border-slate-100 bg-white p-6 shadow-card sm:p-8", children: status === "done" ? (_jsxs("div", { className: "flex flex-col items-center py-10 text-center", children: [_jsx(CheckCircle2, { className: "h-14 w-14 text-brand-600" }), _jsx("h2", { className: "mt-4 text-2xl font-bold text-ink", children: "Thank you!" }), _jsx("p", { className: "mt-2 max-w-sm text-ink-muted", children: "We\u2019ve received your message and our team will get back to you shortly. Need a faster reply?" }), _jsxs("a", { href: whatsappLink("Hi! I just submitted a request on your website."), target: "_blank", rel: "noopener noreferrer", className: "mt-5 inline-flex h-11 items-center gap-2 rounded-lg bg-brand-600 px-5 text-sm font-semibold text-white hover:bg-brand-700", children: [_jsx(MessageCircle, { className: "h-4 w-4" }), " Message us on WhatsApp"] })] })) : (_jsxs("form", { onSubmit: onSubmit, className: "space-y-5", noValidate: true, children: [_jsxs("div", { className: "grid gap-5 sm:grid-cols-2", children: [_jsx(Field, { label: "Your name", required: true, error: errors.name, children: _jsx("input", { className: inputCls(errors.name), value: form.name, onChange: (e) => set("name", e.target.value), placeholder: "e.g. Ahmed Khan", autoComplete: "name" }) }), _jsx(Field, { label: "Business name", required: true, error: errors.business_name, children: _jsx("input", { className: inputCls(errors.business_name), value: form.business_name, onChange: (e) => set("business_name", e.target.value), placeholder: "e.g. Khan Super Store", autoComplete: "organization" }) }), _jsx(Field, { label: "Phone / WhatsApp", required: true, error: errors.phone, children: _jsx("input", { className: inputCls(errors.phone), value: form.phone, onChange: (e) => set("phone", e.target.value), placeholder: "03xx xxxxxxx", inputMode: "tel", autoComplete: "tel" }) }), _jsx(Field, { label: "Email (optional)", error: errors.email, children: _jsx("input", { className: inputCls(errors.email), value: form.email, onChange: (e) => set("email", e.target.value), placeholder: "you@business.com", inputMode: "email", autoComplete: "email" }) }), _jsx(Field, { label: "City (optional)", children: _jsx("input", { className: inputCls(), value: form.city, onChange: (e) => set("city", e.target.value), placeholder: "e.g. Lahore", autoComplete: "address-level2" }) }), _jsx(Field, { label: "Business type", children: _jsxs("select", { className: inputCls(), value: form.business_type, onChange: (e) => set("business_type", e.target.value), children: [_jsx("option", { value: "", children: "Select\u2026" }), BUSINESS_TYPES.map((b) => (_jsx("option", { value: b, children: b }, b)))] }) })] }), _jsx(Field, { label: "What are you interested in?", required: true, error: errors.product_interest, children: _jsx("div", { className: "grid grid-cols-3 gap-2", children: [
                                                    ["pos", "POS Terminal"],
                                                    ["digital_invoicing", "Digital Invoicing"],
                                                    ["both", "Both"],
                                                ].map(([val, label]) => (_jsx("button", { type: "button", onClick: () => set("product_interest", val), className: cn("rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors", form.product_interest === val
                                                        ? "border-brand-600 bg-brand-50 text-brand-700"
                                                        : "border-slate-200 text-ink-soft hover:border-brand-300"), children: label }, val))) }) }), _jsx(Field, { label: "Message (optional)", children: _jsx("textarea", { className: cn(inputCls(), "min-h-[110px] resize-y"), value: form.message, onChange: (e) => set("message", e.target.value), placeholder: "Tell us about your business \u2014 number of shops, what you sell, anything specific\u2026" }) }), _jsx("div", { className: "hidden", "aria-hidden": true, children: _jsxs("label", { children: ["Company website", _jsx("input", { tabIndex: -1, autoComplete: "off", value: form.company_website, onChange: (e) => set("company_website", e.target.value) })] }) }), status === "error" && errorMsg && (_jsx("p", { className: "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700", children: errorMsg })), _jsx(Button, { type: "submit", size: "lg", disabled: status === "sending", className: "w-full sm:w-auto", children: status === "sending" ? "Sending…" : "Send message" }), _jsx("p", { className: "text-xs text-ink-muted", children: "By submitting, you agree to be contacted about InvoiceSolution. We never share your details." })] })) }) }), _jsx(Reveal, { delay: 0.1, children: _jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "rounded-2xl border border-slate-100 bg-white p-6 shadow-soft", children: [_jsx("h3", { className: "font-semibold text-ink", children: "Prefer to talk now?" }), _jsx("p", { className: "mt-1 text-sm text-ink-muted", children: "We usually reply within a few hours." }), _jsxs("div", { className: "mt-5 space-y-3", children: [_jsx(ContactRow, { icon: MessageCircle, label: "WhatsApp", value: "Chat with us", href: whatsappLink("Hi! I'd like a demo of InvoiceSolution.") }), _jsx(ContactRow, { icon: Phone, label: "Phone", value: SITE.phoneDisplay, href: `tel:${SITE.phoneTel}` }), _jsx(ContactRow, { icon: Mail, label: "Email", value: SITE.email, href: `mailto:${SITE.email}` }), _jsx(ContactRow, { icon: MapPin, label: "Location", value: SITE.city })] })] }), _jsxs("div", { className: "overflow-hidden rounded-2xl border border-brand-100 bg-brand-50 p-6", children: [_jsx("h3", { className: "font-semibold text-brand-900", children: "Already a customer?" }), _jsx("p", { className: "mt-1 text-sm text-brand-800/80", children: "Sign in to your dashboard to manage invoices, stock and reports." }), _jsx("a", { href: SITE.appUrl, target: "_blank", rel: "noopener noreferrer", className: "mt-4 inline-flex h-10 items-center rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700", children: "Go to login \u2192" })] })] }) })] }) })] }));
}
function Field({ label, required, error, children, }) {
    return (_jsxs("label", { className: "block", children: [_jsxs("span", { className: "mb-1.5 block text-sm font-medium text-ink", children: [label, " ", required && _jsx("span", { className: "text-brand-600", children: "*" })] }), children, error && _jsx("span", { className: "mt-1 block text-xs text-red-600", children: error[0] })] }));
}
function inputCls(error) {
    return cn("h-11 w-full rounded-lg border bg-white px-3.5 text-sm text-ink shadow-sm outline-none transition-colors placeholder:text-ink-muted/70", "focus:border-brand-500 focus:ring-2 focus:ring-brand-100", error ? "border-red-300" : "border-slate-200");
}
function ContactRow({ icon: Icon, label, value, href, }) {
    const inner = (_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600", children: _jsx(Icon, { className: "h-4 w-4" }) }), _jsxs("span", { children: [_jsx("span", { className: "block text-xs text-ink-muted", children: label }), _jsx("span", { className: "block text-sm font-medium text-ink", children: value })] })] }));
    return href ? (_jsx("a", { href: href, target: href.startsWith("http") ? "_blank" : undefined, rel: "noopener noreferrer", className: "block rounded-lg transition-colors hover:bg-slate-50", children: inner })) : (inner);
}
