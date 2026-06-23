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
    description:
      "FBR compliance, offline-first sales, every payment method, multi-branch inventory, reports, returns, roles and hardware — explore the full feature set.",
    path: "/features",
  });

  return (
    <>
      <PageHero
        eyebrow="Features"
        title="A complete toolkit to run a compliant business"
        lead="Everything from the first scan to the FBR-validated receipt — and every report, return and role in between."
      >
        <ButtonLink to="/contact" size="lg">
          Book a demo
        </ButtonLink>
      </PageHero>

      {FEATURE_GROUPS.map((group, i) => (
        <section
          key={group.category}
          className={i % 2 === 1 ? "bg-slate-50/60" : undefined}
        >
          <div className="container section">
            <Reveal>
              <div className="mb-10 max-w-2xl">
                <span className="eyebrow">{group.category}</span>
                <p className="lead mt-4">{group.blurb}</p>
              </div>
            </Reveal>
            <FeatureGrid features={group.features} columns={3} />
          </div>
        </section>
      ))}

      <CtaBand />
    </>
  );
}
