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
    description:
      "FBR-compliant POS and Digital Invoicing for Pakistani businesses. Real FBR invoice numbers, scannable QR receipts, all payment methods, and software that works even offline.",
    path: "/",
  });

  return (
    <>
      <Hero />
      <TrustStrip />
      <ProductSplit />

      <div className="bg-slate-50/60">
        <div className="container section">
          <SectionHeading
            eyebrow="Everything you need"
            title="One system to run and report your business"
            lead="From the first scan to the FBR-validated receipt — and every report in between."
          />
          <FeatureGrid features={HOME_FEATURES} columns={4} />
        </div>
      </div>

      <OfflineStory />
      <PaymentMarquee />

      <div className="py-12">
        <Stats />
      </div>

      <IndustryCards />

      <div className="bg-slate-50/60">
        <div className="container section">
          <SectionHeading
            eyebrow="Simple, honest pricing"
            title="Plans that grow with you"
            lead="Start with a single shop and scale to unlimited branches. All plans are fully FBR-compliant."
          />
          <PricingCards compact />
        </div>
      </div>

      <CtaBand />
    </>
  );
}
