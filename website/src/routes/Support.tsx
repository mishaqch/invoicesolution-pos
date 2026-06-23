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
    description:
      "Get help with InvoiceSolution: FAQs, WhatsApp, phone and email support, and a simple guided onboarding process.",
    path: "/support",
  });

  return (
    <>
      <PageHero
        eyebrow="Support"
        title="Help, whenever you need it"
        lead="Real people who know FBR and know retail. Reach us on WhatsApp, phone or email — or find a quick answer below."
      />

      {/* Channels */}
      <section className="container -mt-6 pb-8">
        <div className="grid gap-5 md:grid-cols-3">
          {CHANNELS.map((c, i) => (
            <Reveal key={c.title} delay={i * 0.07}>
              <div className="flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-7 text-center shadow-card">
                <span className="mx-auto mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                  <c.icon className="h-6 w-6" />
                </span>
                <h3 className="text-lg font-semibold text-ink">{c.title}</h3>
                <p className="mt-1 flex-1 text-sm text-ink-muted">{c.desc}</p>
                <ButtonAnchor href={c.action.href} variant="secondary" className="mt-5">
                  {c.action.label}
                </ButtonAnchor>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Onboarding steps */}
      <section className="bg-slate-50/60">
        <div className="container section">
          <SectionHeading
            eyebrow="Getting started"
            title="From sign-up to selling in days"
            lead="Onboarding is guided — you're never left to figure out FBR on your own."
          />
          <div className="grid gap-6 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <Reveal key={s.t} delay={i * 0.08}>
                <div className="relative h-full rounded-2xl border border-slate-100 bg-white p-6 shadow-soft">
                  <div className="mb-3 text-sm font-bold text-brand-600">Step {i + 1}</div>
                  <s.icon className="h-6 w-6 text-brand-600" />
                  <h3 className="mt-3 font-semibold text-ink">{s.t}</h3>
                  <p className="mt-1.5 text-sm text-ink-muted">{s.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="container section">
        <SectionHeading eyebrow="FAQ" title="Frequently asked questions" center />
        <div className="mx-auto max-w-3xl">
          <Accordion items={FAQS} />
        </div>
        <div className="mx-auto mt-10 max-w-xl rounded-2xl border border-slate-100 bg-white p-7 text-center shadow-soft">
          <h3 className="text-lg font-semibold text-ink">Still have a question?</h3>
          <p className="mt-1.5 text-sm text-ink-muted">
            Our team replies fast. Book a demo or message us and we&rsquo;ll help you get set up.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <ButtonLink to="/contact">Contact us</ButtonLink>
            <ButtonAnchor href={SITE.appUrl} variant="secondary">
              <LogIn className="h-4 w-4" /> Existing customer login
            </ButtonAnchor>
          </div>
        </div>
      </section>
    </>
  );
}
