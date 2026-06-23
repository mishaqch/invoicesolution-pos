import {
  Boxes,
  Check,
  CreditCard,
  FileText,
  Monitor,
  Printer,
  ScanLine,
  Send,
  ShieldCheck,
  Store,
  Warehouse,
  WifiOff,
} from "lucide-react";

import { CtaBand } from "@/components/sections/CtaBand";
import { PageHero } from "@/components/sections/PageHero";
import { ReceiptMock } from "@/components/sections/ReceiptMock";
import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { useSeo } from "@/lib/useSeo";

const POS_POINTS = [
  { icon: WifiOff, t: "Offline-first", d: "Keep selling through power cuts and internet outages; auto-syncs when back online." },
  { icon: ScanLine, t: "Barcode checkout", d: "Plug-and-play USB scanners with no drivers — just scan and sell." },
  { icon: Printer, t: "Thermal receipts", d: "58mm and 80mm ESC/POS printers with FBR logo and scannable QR." },
  { icon: Monitor, t: "Customer display", d: "Show items and the running total on a second screen for the customer." },
  { icon: CreditCard, t: "All payment methods", d: "Cash, card, wallets, Raast, cheque, bank, store credit — and split payments." },
  { icon: Store, t: "Multi-branch & multi-till", d: "Run several terminals per shop, all syncing to one central account." },
];

const DI_POINTS = [
  { icon: FileText, t: "No hardware needed", d: "Raise FBR-compliant invoices straight from your browser — no till required." },
  { icon: Warehouse, t: "Multi-warehouse stock", d: "Track on-hand across warehouses with transfers and audits." },
  { icon: Send, t: "Direct FBR submission", d: "Validate and submit to FBR Digital Invoicing, with real invoice numbers and QR." },
  { icon: Boxes, t: "High invoice volumes", d: "Built for wholesalers and distributors issuing many invoices a day." },
  { icon: ShieldCheck, t: "Edit & cancel rules", d: "72-hour edit window and monthly cancel limits enforced exactly per FBR." },
];

export default function Products() {
  useSeo({
    title: "Products — POS Terminal & Digital Invoicing",
    description:
      "Two FBR-compliant products: an offline-first POS Terminal for counter-side shops, and Digital Invoicing for back-office invoicing without hardware.",
    path: "/products",
  });

  return (
    <>
      <PageHero
        eyebrow="Products"
        title="Two ways to invoice, both 100% FBR-compliant"
        lead="A counter-side POS for shops, and back-office Digital Invoicing for everyone else. Use one — or both."
      >
        <ButtonLink to="/contact" size="lg">
          Book a demo
        </ButtonLink>
        <ButtonLink to="/pricing" variant="secondary" size="lg">
          See pricing
        </ButtonLink>
      </PageHero>

      {/* POS */}
      <section id="pos" className="container section scroll-mt-20">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <Reveal>
            <span className="eyebrow">POS Terminal</span>
            <h2 className="h2 mt-4">The fastest FBR-ready counter in Pakistan</h2>
            <p className="lead mt-4">
              Scan, ring up, take any payment and print an FBR receipt in seconds. The terminal runs
              on affordable Windows hardware and keeps working when your connection doesn&rsquo;t.
            </p>
            <div className="mt-8 grid gap-5 sm:grid-cols-2">
              {POS_POINTS.map((p) => (
                <div key={p.t} className="flex gap-3">
                  <p.icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                  <div>
                    <div className="font-semibold text-ink">{p.t}</div>
                    <div className="text-sm text-ink-muted">{p.d}</div>
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
          <Reveal delay={0.1}>
            <ReceiptMock />
          </Reveal>
        </div>
      </section>

      {/* Digital Invoicing */}
      <section id="digital-invoicing" className="scroll-mt-20 bg-slate-50/60">
        <div className="container section">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <Reveal className="lg:order-2">
              <span className="eyebrow">Digital Invoicing</span>
              <h2 className="h2 mt-4">FBR invoices from your browser</h2>
              <p className="lead mt-4">
                For wholesalers, distributors, importers and service providers who invoice from the
                office. No printer, no scanner, no till — just compliant invoices, fast.
              </p>
              <div className="mt-8 grid gap-5 sm:grid-cols-2">
                {DI_POINTS.map((p) => (
                  <div key={p.t} className="flex gap-3">
                    <p.icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                    <div>
                      <div className="font-semibold text-ink">{p.t}</div>
                      <div className="text-sm text-ink-muted">{p.d}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>
            <Reveal delay={0.1} className="lg:order-1">
              <DiMock />
            </Reveal>
          </div>
        </div>
      </section>

      {/* Which is right */}
      <section className="container section">
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow">Not sure which?</span>
          <h2 className="h2 mt-4">Which product is right for me?</h2>
        </div>
        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <Reveal>
            <ChooseCard
              title="Choose POS Terminal if…"
              items={[
                "You sell over a counter with a till",
                "You need barcode scanning & thermal receipts",
                "You're a retailer, pharmacy or restaurant",
                "You want to keep selling during outages",
              ]}
            />
          </Reveal>
          <Reveal delay={0.08}>
            <ChooseCard
              title="Choose Digital Invoicing if…"
              items={[
                "You invoice from a back office, not a counter",
                "You're a wholesaler, distributor or service provider",
                "You don't need printers or scanners",
                "You issue many invoices across warehouses",
              ]}
            />
          </Reveal>
        </div>
        <p className="mt-8 text-center text-sm text-ink-muted">
          Need both? Many businesses run the POS and Digital Invoicing together — we&rsquo;ll set up the
          right mix for you.
        </p>
      </section>

      <CtaBand />
    </>
  );
}

function ChooseCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="h-full rounded-2xl border border-slate-100 bg-white p-7 shadow-card">
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      <ul className="mt-5 space-y-3">
        {items.map((it) => (
          <li key={it} className="flex items-start gap-2.5 text-ink-soft">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" /> {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Simple dashboard-style mock for the Digital Invoicing section. */
function DiMock() {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-ink">Invoices</span>
        <span className="rounded-lg bg-brand-600 px-3 py-1 text-xs font-semibold text-white">
          + New invoice
        </span>
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-100">
        {[
          ["INV-2026-0481", "Al-Karam Traders", "Rs 128,400.00", "Valid"],
          ["INV-2026-0480", "Hassan Distributors", "Rs 54,900.00", "Valid"],
          ["INV-2026-0479", "Metro Wholesale", "Rs 312,750.00", "Valid"],
          ["INV-2026-0478", "City Pharma", "Rs 18,250.00", "Pending"],
        ].map(([no, buyer, amt, status], i) => (
          <div
            key={no}
            className={`grid grid-cols-[1fr_auto] items-center gap-2 px-4 py-3 text-[13px] ${
              i % 2 ? "bg-slate-50/60" : "bg-white"
            }`}
          >
            <div>
              <div className="font-mono text-xs text-ink-muted">{no}</div>
              <div className="font-medium text-ink">{buyer}</div>
            </div>
            <div className="text-right">
              <div className="font-mono text-ink">{amt}</div>
              <span
                className={`text-[11px] font-semibold ${
                  status === "Valid" ? "text-brand-700" : "text-amber-600"
                }`}
              >
                {status === "Valid" ? "✓ " : "• "}
                {status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
