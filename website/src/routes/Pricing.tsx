import { Check, Minus } from "lucide-react";

import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { PricingCards } from "@/components/sections/PricingCards";
import { Accordion } from "@/components/ui/Accordion";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { COMPARISON, PLANS } from "@/data/plans";
import { useSeo } from "@/lib/useSeo";

const PRICING_FAQ = [
  { q: "Is there a free trial?", a: "Yes — new accounts include a 14-day trial so you can see InvoiceSolution working with your own products before you commit." },
  { q: "How do I pay for my subscription?", a: "You can pay by bank transfer, JazzCash Business, EasyPaisa Business or Raast. Our team shares the details during onboarding." },
  { q: "Can I change plans later?", a: "Absolutely. Start on Starter and move up to Pro or Enterprise as you add branches, terminals or team members — just let us know." },
  { q: "Do prices include FBR fees?", a: "Our subscription covers the InvoiceSolution software and FBR Digital Invoicing integration. Any fees charged directly by FBR/PRAL to your business are separate." },
];

function rs(n: number) {
  return n.toLocaleString("en-PK");
}

export default function Pricing() {
  useSeo({
    title: "Pricing — Simple plans in PKR",
    description:
      "Transparent pricing for InvoiceSolution: Starter Rs 2,000/mo, Pro Rs 5,000/mo, Enterprise Rs 15,000/mo. All plans fully FBR-compliant. 14-day trial.",
    path: "/pricing",
  });

  return (
    <>
      <PageHero
        eyebrow="Pricing"
        title="Simple, transparent pricing"
        lead="Every plan is fully FBR-compliant and offline-first. Pay monthly or save with yearly. All prices in PKR."
      />

      <section className="container pb-8">
        <PricingCards />
      </section>

      {/* Comparison table */}
      <section className="bg-slate-50/60">
        <div className="container section">
          <SectionHeading eyebrow="Compare" title="Everything in each plan" center />
          <Reveal>
            <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white shadow-soft">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="px-5 py-4 text-left font-semibold text-ink">Feature</th>
                    {PLANS.map((p) => (
                      <th key={p.name} className="px-5 py-4 text-center font-semibold text-ink">
                        <div>{p.name}</div>
                        <div className="text-xs font-normal text-ink-muted">
                          Rs {rs(p.monthly)}/mo
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map((row, i) => (
                    <tr key={row.label} className={i % 2 ? "bg-slate-50/50" : undefined}>
                      <td className="px-5 py-3 text-ink-soft">{row.label}</td>
                      {row.values.map((v, j) => (
                        <td key={j} className="px-5 py-3 text-center">
                          {v === "✓" ? (
                            <Check className="mx-auto h-4 w-4 text-brand-600" />
                          ) : v === "—" ? (
                            <Minus className="mx-auto h-4 w-4 text-slate-300" />
                          ) : (
                            <span className="font-medium text-ink">{v}</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Pricing FAQ */}
      <section className="container section">
        <SectionHeading eyebrow="Questions" title="Pricing FAQ" center />
        <div className="mx-auto max-w-3xl">
          <Accordion items={PRICING_FAQ} />
        </div>
      </section>

      <CtaBand title="Try it with your own products" subtitle="Start your 14-day trial — we'll set everything up and walk you through it." />
    </>
  );
}
