import { CloudOff, RefreshCw, Wifi } from "lucide-react";

import { Reveal } from "@/components/ui/Reveal";

const STEPS = [
  {
    icon: CloudOff,
    dot: "bg-amber-500",
    title: "Internet drops",
    desc: "A power cut or a dead connection — it happens. Your cashier keeps ringing up sales without missing a beat.",
  },
  {
    icon: RefreshCw,
    dot: "bg-amber-500",
    title: "Saved locally",
    desc: "Every sale is written safely to the terminal's own database first, queued and waiting — never lost.",
  },
  {
    icon: Wifi,
    dot: "bg-brand-500",
    title: "Back online — auto-syncs",
    desc: "The moment you reconnect, queued invoices sync to the cloud and to FBR automatically, with no duplicates.",
  },
];

/** "Works offline" explainer — the strongest differentiator for PK shops. */
export function OfflineStory() {
  return (
    <div className="relative overflow-hidden bg-ink">
      <div aria-hidden className="absolute inset-0 opacity-[0.07] bg-grid-faint bg-[size:40px_40px]" />
      <div
        aria-hidden
        className="absolute -left-20 top-0 h-72 w-72 rounded-full bg-brand-600/20 blur-3xl"
      />
      <div className="container section relative">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-brand-300">
            Offline-first
          </span>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Your shop never stops
          </h2>
          <p className="mt-4 text-lg text-slate-300">
            Built for real Pakistani conditions. When the internet or power goes down,
            InvoiceSolution keeps selling — and quietly catches up the moment it&rsquo;s back.
          </p>
        </div>

        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 0.1}>
              <div className="relative h-full rounded-2xl border border-white/10 bg-white/[0.04] p-6 backdrop-blur">
                <div className="mb-4 flex items-center gap-3">
                  <span className={`relative flex h-3 w-3`}>
                    <span className={`absolute inline-flex h-full w-full animate-pulse-dot rounded-full ${s.dot}`} />
                    <span className={`relative inline-flex h-3 w-3 rounded-full ${s.dot}`} />
                  </span>
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Step {i + 1}
                  </span>
                </div>
                <s.icon className="h-7 w-7 text-brand-400" />
                <h3 className="mt-4 text-lg font-semibold text-white">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">{s.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </div>
  );
}
