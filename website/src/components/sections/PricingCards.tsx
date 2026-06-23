import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Reveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/cn";
import { PLANS } from "@/data/plans";

function rs(n: number) {
  return n.toLocaleString("en-PK");
}

/** Pricing cards with a monthly/yearly toggle. Reused on Home + Pricing. */
export function PricingCards({ compact = false }: { compact?: boolean }) {
  const [yearly, setYearly] = useState(false);

  return (
    <div>
      <div className="mb-10 flex items-center justify-center">
        <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-soft">
          <ToggleBtn active={!yearly} onClick={() => setYearly(false)}>
            Monthly
          </ToggleBtn>
          <ToggleBtn active={yearly} onClick={() => setYearly(true)}>
            Yearly
            <span className="ml-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-bold text-brand-700">
              ~2 months free
            </span>
          </ToggleBtn>
        </div>
      </div>

      <div className="grid items-stretch gap-6 lg:grid-cols-3">
        {PLANS.map((plan, i) => {
          const price = yearly ? plan.yearly : plan.monthly;
          const period = yearly ? "/year" : "/month";
          return (
            <Reveal key={plan.name} delay={i * 0.08}>
              <div
                className={cn(
                  "relative flex h-full flex-col rounded-2xl border bg-white p-7 shadow-card",
                  plan.highlight ? "border-brand-300 ring-2 ring-brand-200" : "border-slate-100",
                )}
              >
                {plan.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-1 text-xs font-bold text-white shadow-sm">
                    Most popular
                  </span>
                )}
                <h3 className="text-lg font-bold text-ink">{plan.name}</h3>
                <p className="mt-1 text-sm text-ink-muted">{plan.tagline}</p>
                <div className="mt-5 flex items-end gap-1">
                  <span className="text-sm font-semibold text-ink-muted">Rs</span>
                  <span className="text-4xl font-extrabold tracking-tight text-ink">{rs(price)}</span>
                  <span className="pb-1 text-sm text-ink-muted">{period}</span>
                </div>

                <Link
                  to="/contact"
                  className={cn(
                    "mt-6 inline-flex h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition-all",
                    plan.highlight
                      ? "bg-brand-600 text-white shadow-glow hover:bg-brand-700"
                      : "border border-slate-200 text-ink hover:border-brand-300 hover:text-brand-700",
                  )}
                >
                  {plan.cta}
                </Link>

                {!compact && (
                  <>
                    <div className="mt-6 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs text-ink-soft">
                      <span>{plan.limits.branches}</span>
                      <span>{plan.limits.terminals}</span>
                      <span>{plan.limits.products}</span>
                      <span>{plan.limits.users}</span>
                    </div>
                    <ul className="mt-6 space-y-3">
                      {plan.features.map((f) => (
                        <li key={f} className="flex items-start gap-2.5 text-sm text-ink-soft">
                          <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>

      <p className="mt-8 text-center text-sm text-ink-muted">
        All prices in PKR. 14-day trial on new accounts. Need something custom?{" "}
        <Link to="/contact" className="font-semibold text-brand-700 hover:underline">
          Talk to us
        </Link>
        .
      </p>
    </div>
  );
}

function ToggleBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center rounded-full px-4 py-2 text-sm font-medium transition-colors",
        active ? "bg-brand-600 text-white" : "text-ink-soft hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}
