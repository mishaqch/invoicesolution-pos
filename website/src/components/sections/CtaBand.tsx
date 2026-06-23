import { ArrowRight, MessageCircle } from "lucide-react";

import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";
import { whatsappLink } from "@/lib/site";

/** Reusable closing call-to-action band. Appears near the foot of most pages. */
export function CtaBand({
  title = "Ready to get FBR-ready?",
  subtitle = "Book a free demo and we'll set up your account, configure FBR, import your products and train your team.",
}: {
  title?: string;
  subtitle?: string;
}) {
  return (
    <div className="container py-16 sm:py-20">
      <div className="relative overflow-hidden rounded-3xl bg-ink px-6 py-14 text-center shadow-card sm:px-12">
        <div aria-hidden className="absolute inset-0 mesh opacity-60" />
        <div
          aria-hidden
          className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-brand-600/30 blur-3xl"
        />
        <div className="relative mx-auto max-w-2xl">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h2>
          <p className="mx-auto mt-4 max-w-xl text-lg text-slate-300">{subtitle}</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <ButtonLink to="/contact" variant="white" size="lg">
              Book a free demo <ArrowRight className="h-4 w-4" />
            </ButtonLink>
            <ButtonAnchor
              href={whatsappLink("Hi! I'd like a demo of InvoiceSolution.")}
              variant="secondary"
              size="lg"
              className="border-white/20 bg-white/5 text-white hover:bg-white/10 hover:text-white"
            >
              <MessageCircle className="h-4 w-4" /> WhatsApp us
            </ButtonAnchor>
          </div>
        </div>
      </div>
    </div>
  );
}
