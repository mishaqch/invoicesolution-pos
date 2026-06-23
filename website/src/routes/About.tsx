import { HeartHandshake, ShieldCheck, Sparkles, Zap } from "lucide-react";

import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { Stats } from "@/components/sections/Stats";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { useSeo } from "@/lib/useSeo";

const VALUES = [
  { icon: ShieldCheck, t: "Compliance, done right", d: "FBR rules are complex and change often. We do the hard work so your invoices are always correct." },
  { icon: Zap, t: "Built for reality", d: "Power cuts and patchy internet are facts of life here. Our software is designed to keep working anyway." },
  { icon: HeartHandshake, t: "Real support", d: "You're never left alone with a screen. Our team helps you onboard and stays a WhatsApp away." },
  { icon: Sparkles, t: "Honest & simple", d: "Clear pricing, no jargon, no surprises. We build software shopkeepers actually enjoy using." },
];

export default function About() {
  useSeo({
    title: "About — Built for Pakistani businesses",
    description:
      "InvoiceSolution is an FBR-compliant POS and Digital Invoicing platform, built in Pakistan for Pakistani businesses.",
    path: "/about",
  });

  return (
    <>
      <PageHero
        eyebrow="About us"
        title="Software that helps Pakistani businesses thrive — and stay compliant"
        lead="We started InvoiceSolution to make FBR compliance painless for the shops, pharmacies, restaurants and distributors that power Pakistan's economy."
      />

      <section className="container section">
        <div className="mx-auto max-w-3xl space-y-6 text-lg leading-relaxed text-ink-soft">
          <Reveal>
            <p>
              FBR Digital Invoicing is now a fact of business life in Pakistan — but the tools to
              comply have often been expensive, complicated, or fragile when the internet drops.
              We thought retailers deserved better.
            </p>
          </Reveal>
          <Reveal delay={0.05}>
            <p>
              So we built a system that does both halves of the job well: a fast, friendly Point of
              Sale and Digital Invoicing experience your team will love, sitting on top of a rock-solid,
              <span className="font-semibold text-ink"> offline-first</span> engine that keeps selling
              through outages and syncs to FBR automatically.
            </p>
          </Reveal>
          <Reveal delay={0.1}>
            <p>
              From a single corner store to a multi-warehouse distributor, InvoiceSolution scales with
              you — with real FBR invoice numbers, scannable QR receipts, and a six-year audit trail
              built in from day one.
            </p>
          </Reveal>
        </div>
      </section>

      <div className="pb-4">
        <Stats />
      </div>

      <section className="bg-slate-50/60">
        <div className="container section">
          <SectionHeading eyebrow="What we believe" title="The principles behind the product" center />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {VALUES.map((v, i) => (
              <Reveal key={v.t} delay={i * 0.07}>
                <div className="h-full rounded-2xl border border-slate-100 bg-white p-6 shadow-soft">
                  <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                    <v.icon className="h-5 w-5" />
                  </span>
                  <h3 className="font-semibold text-ink">{v.t}</h3>
                  <p className="mt-1.5 text-sm text-ink-muted">{v.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <CtaBand />
    </>
  );
}
