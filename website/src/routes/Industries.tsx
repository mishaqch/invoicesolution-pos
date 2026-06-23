import { Check } from "lucide-react";

import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { ButtonLink } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
import { INDUSTRIES } from "@/data/industries";
import { useSeo } from "@/lib/useSeo";

export default function Industries() {
  useSeo({
    title: "Industries — Built for your trade",
    description:
      "Retail, pharmacy, restaurant, wholesale, service providers and importers/exporters — InvoiceSolution adapts to how your business works.",
    path: "/industries",
  });

  return (
    <>
      <PageHero
        eyebrow="Industries"
        title="Shaped to fit how you work"
        lead="One FBR-compliant platform, tuned for the realities of each trade — from a corner store to a multi-warehouse distributor."
      >
        <ButtonLink to="/contact" size="lg">
          Book a demo
        </ButtonLink>
      </PageHero>

      {INDUSTRIES.map((ind, i) => (
        <section
          key={ind.id}
          id={ind.id}
          className={`scroll-mt-20 ${i % 2 === 1 ? "bg-slate-50/60" : ""}`}
        >
          <div className="container section">
            <div className="grid items-center gap-10 lg:grid-cols-2">
              <Reveal className={i % 2 === 1 ? "lg:order-2" : ""}>
                <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100">
                  <Icon name={ind.icon} className="h-6 w-6" />
                </div>
                <span className="eyebrow">{ind.name}</span>
                <h2 className="h2 mt-3">{ind.headline}</h2>
                <p className="lead mt-4">{ind.desc}</p>
                <ButtonLink to="/contact" className="mt-7">
                  Talk to us about {ind.name.toLowerCase()}
                </ButtonLink>
              </Reveal>

              <Reveal delay={0.1} className={i % 2 === 1 ? "lg:order-1" : ""}>
                <div className="grid gap-3 sm:grid-cols-2">
                  {ind.points.map((pt) => (
                    <div
                      key={pt}
                      className="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-4 shadow-soft"
                    >
                      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50">
                        <Check className="h-4 w-4 text-brand-600" />
                      </span>
                      <span className="text-sm font-medium text-ink">{pt}</span>
                    </div>
                  ))}
                </div>
              </Reveal>
            </div>
          </div>
        </section>
      ))}

      <CtaBand />
    </>
  );
}
