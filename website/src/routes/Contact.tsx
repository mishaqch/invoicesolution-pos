import { CheckCircle2, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { useState } from "react";

import { PageHero } from "@/components/sections/PageHero";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { LeadError, submitLead, type LeadPayload } from "@/lib/api";
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

const emptyForm: LeadPayload = {
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
    description:
      "Get in touch to book a free demo of InvoiceSolution. We'll set up your FBR-compliant POS or Digital Invoicing account and train your team.",
    path: "/contact",
  });

  const [form, setForm] = useState<LeadPayload>(emptyForm);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  function set<K extends keyof LeadPayload>(key: K, value: LeadPayload[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function clientValidate(): boolean {
    const e: Record<string, string[]> = {};
    if (!form.name.trim()) e.name = ["Please enter your name."];
    if (!form.business_name.trim()) e.business_name = ["Please enter your business name."];
    if (!form.phone.trim()) e.phone = ["Please enter a phone number."];
    else if (!/^[0-9+\-\s()]{7,}$/.test(form.phone)) e.phone = ["Enter a valid phone number."];
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = ["Enter a valid email."];
    if (!form.product_interest) e.product_interest = ["Please choose what you're interested in."];
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    setErrorMsg("");
    if (!clientValidate()) return;
    setStatus("sending");
    try {
      await submitLead(form);
      setStatus("done");
      setForm(emptyForm);
    } catch (err) {
      if (err instanceof LeadError) {
        setErrorMsg(err.message);
        if (err.fields) setErrors(err.fields);
      } else {
        setErrorMsg("Something went wrong. Please try again.");
      }
      setStatus("error");
    }
  }

  return (
    <>
      <PageHero
        eyebrow="Contact"
        title="Let's get your business FBR-ready"
        lead="Tell us a little about your shop and we'll be in touch to book your demo and set everything up."
      />

      <section className="container pb-20">
        <div className="grid gap-10 lg:grid-cols-[1.3fr_1fr]">
          {/* Form */}
          <Reveal>
            <div className="rounded-2xl border border-slate-100 bg-white p-6 shadow-card sm:p-8">
              {status === "done" ? (
                <div className="flex flex-col items-center py-10 text-center">
                  <CheckCircle2 className="h-14 w-14 text-brand-600" />
                  <h2 className="mt-4 text-2xl font-bold text-ink">Thank you!</h2>
                  <p className="mt-2 max-w-sm text-ink-muted">
                    We&rsquo;ve received your message and our team will get back to you shortly. Need a
                    faster reply?
                  </p>
                  <a
                    href={whatsappLink("Hi! I just submitted a request on your website.")}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-5 inline-flex h-11 items-center gap-2 rounded-lg bg-brand-600 px-5 text-sm font-semibold text-white hover:bg-brand-700"
                  >
                    <MessageCircle className="h-4 w-4" /> Message us on WhatsApp
                  </a>
                </div>
              ) : (
                <form onSubmit={onSubmit} className="space-y-5" noValidate>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="Your name" required error={errors.name}>
                      <input
                        className={inputCls(errors.name)}
                        value={form.name}
                        onChange={(e) => set("name", e.target.value)}
                        placeholder="e.g. Ahmed Khan"
                        autoComplete="name"
                      />
                    </Field>
                    <Field label="Business name" required error={errors.business_name}>
                      <input
                        className={inputCls(errors.business_name)}
                        value={form.business_name}
                        onChange={(e) => set("business_name", e.target.value)}
                        placeholder="e.g. Khan Super Store"
                        autoComplete="organization"
                      />
                    </Field>
                    <Field label="Phone / WhatsApp" required error={errors.phone}>
                      <input
                        className={inputCls(errors.phone)}
                        value={form.phone}
                        onChange={(e) => set("phone", e.target.value)}
                        placeholder="03xx xxxxxxx"
                        inputMode="tel"
                        autoComplete="tel"
                      />
                    </Field>
                    <Field label="Email (optional)" error={errors.email}>
                      <input
                        className={inputCls(errors.email)}
                        value={form.email}
                        onChange={(e) => set("email", e.target.value)}
                        placeholder="you@business.com"
                        inputMode="email"
                        autoComplete="email"
                      />
                    </Field>
                    <Field label="City (optional)">
                      <input
                        className={inputCls()}
                        value={form.city}
                        onChange={(e) => set("city", e.target.value)}
                        placeholder="e.g. Lahore"
                        autoComplete="address-level2"
                      />
                    </Field>
                    <Field label="Business type">
                      <select
                        className={inputCls()}
                        value={form.business_type}
                        onChange={(e) => set("business_type", e.target.value)}
                      >
                        <option value="">Select…</option>
                        {BUSINESS_TYPES.map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>

                  <Field label="What are you interested in?" required error={errors.product_interest}>
                    <div className="grid grid-cols-3 gap-2">
                      {([
                        ["pos", "POS Terminal"],
                        ["digital_invoicing", "Digital Invoicing"],
                        ["both", "Both"],
                      ] as const).map(([val, label]) => (
                        <button
                          type="button"
                          key={val}
                          onClick={() => set("product_interest", val)}
                          className={cn(
                            "rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
                            form.product_interest === val
                              ? "border-brand-600 bg-brand-50 text-brand-700"
                              : "border-slate-200 text-ink-soft hover:border-brand-300",
                          )}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </Field>

                  <Field label="Message (optional)">
                    <textarea
                      className={cn(inputCls(), "min-h-[110px] resize-y")}
                      value={form.message}
                      onChange={(e) => set("message", e.target.value)}
                      placeholder="Tell us about your business — number of shops, what you sell, anything specific…"
                    />
                  </Field>

                  {/* Honeypot — hidden from humans; bots fill it. */}
                  <div className="hidden" aria-hidden>
                    <label>
                      Company website
                      <input
                        tabIndex={-1}
                        autoComplete="off"
                        value={form.company_website}
                        onChange={(e) => set("company_website", e.target.value)}
                      />
                    </label>
                  </div>

                  {status === "error" && errorMsg && (
                    <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      {errorMsg}
                    </p>
                  )}

                  <Button type="submit" size="lg" disabled={status === "sending"} className="w-full sm:w-auto">
                    {status === "sending" ? "Sending…" : "Send message"}
                  </Button>
                  <p className="text-xs text-ink-muted">
                    By submitting, you agree to be contacted about InvoiceSolution. We never share your
                    details.
                  </p>
                </form>
              )}
            </div>
          </Reveal>

          {/* Contact details */}
          <Reveal delay={0.1}>
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-100 bg-white p-6 shadow-soft">
                <h3 className="font-semibold text-ink">Prefer to talk now?</h3>
                <p className="mt-1 text-sm text-ink-muted">We usually reply within a few hours.</p>
                <div className="mt-5 space-y-3">
                  <ContactRow icon={MessageCircle} label="WhatsApp" value="Chat with us" href={whatsappLink("Hi! I'd like a demo of InvoiceSolution.")} />
                  <ContactRow icon={Phone} label="Phone" value={SITE.phoneDisplay} href={`tel:${SITE.phoneTel}`} />
                  <ContactRow icon={Mail} label="Email" value={SITE.email} href={`mailto:${SITE.email}`} />
                  <ContactRow icon={MapPin} label="Location" value={SITE.city} />
                </div>
              </div>
              <div className="overflow-hidden rounded-2xl border border-brand-100 bg-brand-50 p-6">
                <h3 className="font-semibold text-brand-900">Already a customer?</h3>
                <p className="mt-1 text-sm text-brand-800/80">
                  Sign in to your dashboard to manage invoices, stock and reports.
                </p>
                <a
                  href={SITE.appUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex h-10 items-center rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  Go to login →
                </a>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string[];
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">
        {label} {required && <span className="text-brand-600">*</span>}
      </span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600">{error[0]}</span>}
    </label>
  );
}

function inputCls(error?: string[]) {
  return cn(
    "h-11 w-full rounded-lg border bg-white px-3.5 text-sm text-ink shadow-sm outline-none transition-colors placeholder:text-ink-muted/70",
    "focus:border-brand-500 focus:ring-2 focus:ring-brand-100",
    error ? "border-red-300" : "border-slate-200",
  );
}

function ContactRow({
  icon: Icon,
  label,
  value,
  href,
}: {
  icon: typeof Mail;
  label: string;
  value: string;
  href?: string;
}) {
  const inner = (
    <div className="flex items-center gap-3">
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
        <Icon className="h-4 w-4" />
      </span>
      <span>
        <span className="block text-xs text-ink-muted">{label}</span>
        <span className="block text-sm font-medium text-ink">{value}</span>
      </span>
    </div>
  );
  return href ? (
    <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer" className="block rounded-lg transition-colors hover:bg-slate-50">
      {inner}
    </a>
  ) : (
    inner
  );
}
