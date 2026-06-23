import { Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { Link } from "react-router-dom";

import { Logo } from "@/components/layout/Logo";
import { SITE, whatsappLink } from "@/lib/site";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { to: "/products", label: "POS Terminal" },
      { to: "/products#digital-invoicing", label: "Digital Invoicing" },
      { to: "/features", label: "Features" },
      { to: "/pricing", label: "Pricing" },
    ],
  },
  {
    title: "Solutions",
    links: [
      { to: "/industries#retail", label: "Retail & Grocery" },
      { to: "/industries#pharmacy", label: "Pharmacy" },
      { to: "/industries#restaurant", label: "Restaurant" },
      { to: "/industries#wholesale", label: "Wholesale & Distribution" },
    ],
  },
  {
    title: "Company",
    links: [
      { to: "/about", label: "About us" },
      { to: "/support", label: "Support" },
      { to: "/contact", label: "Contact" },
      { to: "/privacy", label: "Privacy Policy" },
      { to: "/terms", label: "Terms of Service" },
    ],
  },
];

export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="container py-14">
        <div className="grid gap-10 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-ink-muted">
              FBR-compliant Point of Sale &amp; Digital Invoicing, built for Pakistani
              businesses. Real FBR invoice numbers, scannable QR, and software that keeps
              working even when your internet doesn&rsquo;t.
            </p>
            <div className="mt-5 space-y-2 text-sm text-ink-soft">
              <a href={whatsappLink("Hi! I'd like to know more about InvoiceSolution.")} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 hover:text-brand-700">
                <MessageCircle className="h-4 w-4 text-brand-600" /> WhatsApp us
              </a>
              <a href={`tel:${SITE.phoneTel}`} className="flex items-center gap-2 hover:text-brand-700">
                <Phone className="h-4 w-4 text-brand-600" /> {SITE.phoneDisplay}
              </a>
              <a href={`mailto:${SITE.email}`} className="flex items-center gap-2 hover:text-brand-700">
                <Mail className="h-4 w-4 text-brand-600" /> {SITE.email}
              </a>
              <span className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-brand-600" /> {SITE.city}
              </span>
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h3 className="text-sm font-semibold text-ink">{col.title}</h3>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.to + l.label}>
                    <Link to={l.to} className="text-sm text-ink-muted transition-colors hover:text-brand-700">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-4 border-t border-slate-200 pt-6 text-sm text-ink-muted sm:flex-row sm:items-center">
          <p>© {year} {SITE.name}. All rights reserved.</p>
          <p className="max-w-md text-xs leading-relaxed">
            InvoiceSolution integrates with FBR Digital Invoicing via a PRAL-licensed
            integrator. We are an independent software provider and not a government body.
          </p>
        </div>
      </div>
    </footer>
  );
}
