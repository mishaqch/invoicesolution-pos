import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/Section";
import { INDUSTRIES } from "@/data/industries";

/** Grid of industry cards linking into the Industries page anchors. */
export function IndustryCards({ heading = true }: { heading?: boolean }) {
  return (
    <div className="container section">
      {heading && (
        <SectionHeading
          eyebrow="Built for your business"
          title="One platform, many trades"
          lead="From a corner store to a multi-warehouse distributor — InvoiceSolution adapts to how you work."
        />
      )}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {INDUSTRIES.map((ind, i) => (
          <Reveal key={ind.id} delay={(i % 3) * 0.07}>
            <Link
              to={`/industries#${ind.id}`}
              className="group flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-6 shadow-card transition-all hover:-translate-y-1 hover:border-brand-200 hover:shadow-glow"
            >
              <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100">
                <Icon name={ind.icon} className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold text-ink">{ind.name}</h3>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-ink-muted">{ind.headline}</p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700 group-hover:gap-2.5">
                Explore <ArrowRight className="h-4 w-4 transition-all" />
              </span>
            </Link>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
