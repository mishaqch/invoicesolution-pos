/**
 * Pricing tiers — the REAL plans seeded in the production database
 * (apps.platform_admin.SubscriptionPlan). Prices are in PKR.
 *   Starter  Rs 2,000/mo  · Rs 20,000/yr
 *   Pro      Rs 5,000/mo  · Rs 50,000/yr
 *   Enterprise Rs 15,000/mo (negotiated) · Rs 150,000/yr
 * Yearly ≈ 10 months, i.e. ~2 months free.
 */
export interface Plan {
  name: string;
  monthly: number;
  yearly: number;
  tagline: string;
  highlight?: boolean;
  cta: string;
  limits: { branches: string; terminals: string; products: string; users: string };
  features: string[];
}

export const PLANS: Plan[] = [
  {
    name: "Starter",
    monthly: 2000,
    yearly: 20000,
    tagline: "For a single shop getting FBR-ready.",
    cta: "Get started",
    limits: { branches: "1 branch", terminals: "2 terminals", products: "1,000 products", users: "3 users" },
    features: [
      "FBR Digital Invoicing & QR receipts",
      "Offline-first POS terminal",
      "All payment methods",
      "Inventory & stock tracking",
      "Basic sales & tax reports",
      "CSV product import",
      "Email support",
    ],
  },
  {
    name: "Pro",
    monthly: 5000,
    yearly: 50000,
    tagline: "For growing businesses with multiple branches.",
    highlight: true,
    cta: "Get started",
    limits: { branches: "5 branches", terminals: "10 terminals", products: "10,000 products", users: "15 users" },
    features: [
      "Everything in Starter",
      "Multi-branch & warehouse stock",
      "Advanced & scheduled reports",
      "Returns & credit notes",
      "Stock transfers & audits",
      "Phone & WhatsApp support",
      "Priority onboarding",
    ],
  },
  {
    name: "Enterprise",
    monthly: 15000,
    yearly: 150000,
    tagline: "For chains and high-volume operations.",
    cta: "Talk to sales",
    limits: { branches: "Unlimited", terminals: "Unlimited", products: "Unlimited", users: "Unlimited" },
    features: [
      "Everything in Pro",
      "Unlimited branches, tills & users",
      "Dedicated account manager",
      "Custom onboarding & training",
      "SDC/IMS setup for Tier-1 retailers",
      "Priority compliance support",
    ],
  },
];

/** Comparison-table rows (label → value per plan index). */
export const COMPARISON: { label: string; values: [string, string, string] }[] = [
  { label: "Branches", values: ["1", "5", "Unlimited"] },
  { label: "Terminals / tills", values: ["2", "10", "Unlimited"] },
  { label: "Products", values: ["1,000", "10,000", "Unlimited"] },
  { label: "Team members", values: ["3", "15", "Unlimited"] },
  { label: "FBR Digital Invoicing", values: ["✓", "✓", "✓"] },
  { label: "Offline-first POS", values: ["✓", "✓", "✓"] },
  { label: "Multi-warehouse stock", values: ["—", "✓", "✓"] },
  { label: "Advanced & scheduled reports", values: ["—", "✓", "✓"] },
  { label: "Returns & credit notes", values: ["—", "✓", "✓"] },
  { label: "Dedicated account manager", values: ["—", "—", "✓"] },
  { label: "Support", values: ["Email", "Phone + WhatsApp", "Dedicated"] },
];
