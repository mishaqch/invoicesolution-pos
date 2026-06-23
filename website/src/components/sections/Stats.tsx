import { Reveal } from "@/components/ui/Reveal";

const STATS = [
  { value: "100%", label: "FBR-compliant invoicing" },
  { value: "9+", label: "Payment methods supported" },
  { value: "6 yr", label: "Audit retention, built in" },
  { value: "24/7", label: "Sells, even offline" },
];

/** Compact stat strip used on Home / About for credibility. */
export function Stats() {
  return (
    <div className="container">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-slate-100 bg-slate-100 shadow-soft sm:grid-cols-4">
        {STATS.map((s, i) => (
          <Reveal key={s.label} delay={i * 0.06}>
            <div className="bg-white px-6 py-8 text-center">
              <div className="text-3xl font-extrabold tracking-tight text-brand-600 sm:text-4xl">
                {s.value}
              </div>
              <div className="mt-1 text-sm text-ink-muted">{s.label}</div>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
