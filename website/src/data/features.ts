/**
 * Feature catalogue — the single source for feature cards across the site.
 * Every entry here is a feature that ACTUALLY EXISTS in the product (verified
 * against the backend). Icons are lucide-react names resolved in the component.
 */
export interface Feature {
  icon: string; // lucide-react icon name
  title: string;
  desc: string;
}

export interface FeatureGroup {
  category: string;
  blurb: string;
  features: Feature[];
}

export const FEATURE_GROUPS: FeatureGroup[] = [
  {
    category: "FBR & Compliance",
    blurb: "Built for FBR Digital Invoicing from the ground up — not bolted on.",
    features: [
      { icon: "BadgeCheck", title: "Real FBR invoice numbers", desc: "Every invoice is fiscalised through FBR/PRAL and carries the official invoice number — not a locally generated placeholder." },
      { icon: "QrCode", title: "Scannable QR on every receipt", desc: "Customers verify any invoice instantly in the FBR Tax Asaan app. The QR encodes the exact fiscal number." },
      { icon: "ShieldCheck", title: "Tier-1 retailer ready", desc: "Supports both the FBR Digital Invoicing API and the SDC/IMS fiscal path required for large retailers." },
      { icon: "History", title: "6-year audit trail", desc: "Soft-delete plus an append-only audit log keep a tamper-evident record for the full legal retention period." },
      { icon: "Clock", title: "72-hour edit window enforced", desc: "Edit and cancel rules follow the PRAL manual exactly — and are enforced on the server, not just in the UI." },
      { icon: "RefreshCw", title: "Idempotent submission", desc: "Client-generated UUIDs mean a dropped connection never creates a duplicate invoice on FBR." },
    ],
  },
  {
    category: "Sales & Checkout",
    blurb: "A fast counter experience your cashiers will actually enjoy.",
    features: [
      { icon: "ScanLine", title: "Barcode scanning", desc: "Plug-and-play USB scanners (keyboard emulation) — no drivers, no setup." },
      { icon: "PauseCircle", title: "Hold & recall sales", desc: "Park a transaction to serve the next customer, then recall it in one tap." },
      { icon: "Percent", title: "Discounts with controls", desc: "Line and cart discounts (% or rupees), with manager approval thresholds." },
      { icon: "Users", title: "Walk-in or registered buyers", desc: "Sell to walk-ins or attach a registered customer with their NTN/CNIC for compliant invoices." },
      { icon: "Wallet", title: "Day open / close", desc: "Open and close the till with cash reconciliation and variance tracking." },
    ],
  },
  {
    category: "Payments",
    blurb: "Accept every way Pakistani customers want to pay.",
    features: [
      { icon: "Banknote", title: "Cash with change", desc: "Tender, change-due, and rounding handled automatically." },
      { icon: "CreditCard", title: "Card (credit & debit)", desc: "Record card payments with auth code and reference for reconciliation." },
      { icon: "Smartphone", title: "EasyPaisa, JazzCash & Raast", desc: "Wallet and State Bank Raast P2M payments with reference capture." },
      { icon: "Split", title: "Split & credit sales", desc: "Multiple payment methods on one invoice, plus pay-later credit with limits." },
      { icon: "ReceiptText", title: "Cheque, bank & store credit", desc: "Cheque tracking, bank transfers, and customer store-credit balances." },
    ],
  },
  {
    category: "Inventory & Stock",
    blurb: "Know exactly what you have, across every branch and warehouse.",
    features: [
      { icon: "Boxes", title: "Multi-branch & warehouse stock", desc: "Track on-hand per branch and per warehouse, with transfers and in-transit tracking." },
      { icon: "ClipboardList", title: "Append-only stock ledger", desc: "Every movement — sale, return, adjustment — is recorded and fully auditable." },
      { icon: "TriangleAlert", title: "Low-stock alerts", desc: "Reorder reports flag items at or below their threshold before you run out." },
      { icon: "CalendarClock", title: "Batch & expiry tracking", desc: "Batch numbers, expiry dates and FEFO for pharmacies and date-sensitive goods." },
      { icon: "ScrollText", title: "Stock audits & adjustments", desc: "Physical counts with variance reconciliation and reason-tracked adjustments." },
    ],
  },
  {
    category: "Reports & Insights",
    blurb: "The numbers that run your business, in one dashboard.",
    features: [
      { icon: "LineChart", title: "Sales & profit reports", desc: "Daily sales, item-wise and category-wise revenue, units and profit." },
      { icon: "FileSpreadsheet", title: "FBR-formatted tax report", desc: "Tax summaries laid out the way you need them for filing." },
      { icon: "PieChart", title: "Payment & returns breakdown", desc: "See the mix of payment methods and analyse returns at a glance." },
      { icon: "Download", title: "Export anywhere", desc: "Download any report as CSV, Excel or PDF." },
    ],
  },
  {
    category: "Hardware & Terminals",
    blurb: "Works with the affordable hardware you already use.",
    features: [
      { icon: "Printer", title: "Thermal printing", desc: "ESC/POS thermal printers in 58mm and 80mm, with FBR logo and QR on the receipt." },
      { icon: "Monitor", title: "Customer-facing display", desc: "Show the running total and items on a second screen for the customer." },
      { icon: "Inbox", title: "Cash drawer trigger", desc: "Pop the drawer automatically through the printer port on cash sales." },
      { icon: "MonitorSmartphone", title: "Multiple terminals", desc: "Run several tills per shop, each syncing to one central account." },
    ],
  },
  {
    category: "Team & Roles",
    blurb: "The right access for every person on your team.",
    features: [
      { icon: "UserCog", title: "Role-based access", desc: "Owner, Manager, Cashier, Accountant and Auditor roles with the right permissions." },
      { icon: "KeyRound", title: "Fast PIN login", desc: "Cashiers sign in with a PIN; managers approve exceptions with an override." },
      { icon: "FileClock", title: "Activity audit logging", desc: "Sensitive actions are logged so you always know who did what." },
    ],
  },
  {
    category: "Returns & Refunds",
    blurb: "Handle returns cleanly and stay compliant.",
    features: [
      { icon: "Undo2", title: "Returns against invoices", desc: "Full or partial returns linked to the original invoice." },
      { icon: "BadgeDollarSign", title: "Refund or store credit", desc: "Refund to the original method or issue store credit to the customer." },
      { icon: "FileCheck2", title: "FBR credit notes", desc: "Credit notes submitted to FBR within the compliance rules." },
    ],
  },
];

/** Flattened top picks for the homepage feature grid. */
export const HOME_FEATURES: Feature[] = [
  FEATURE_GROUPS[0].features[0], // Real FBR invoice numbers
  { icon: "WifiOff", title: "Works fully offline", desc: "Sales never stop during power cuts or internet outages. Everything syncs automatically when you're back online." },
  FEATURE_GROUPS[2].features[2], // EasyPaisa/JazzCash/Raast
  FEATURE_GROUPS[3].features[0], // Multi-branch & warehouse
  FEATURE_GROUPS[0].features[1], // QR
  FEATURE_GROUPS[5].features[0], // Thermal printing
  FEATURE_GROUPS[4].features[0], // Sales & profit reports
  FEATURE_GROUPS[6].features[0], // Role-based access
];
