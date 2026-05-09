/**
 * Help-center articles. Inline so search is instant and the bundle does
 * not need to fetch JSON over the network. The articles are short on
 * purpose — link to a longer external docs site once it exists.
 */

export interface HelpArticle {
  slug: string;
  title: string;
  summary: string;
  body: string;
  tags: string[];
}

export const ARTICLES: HelpArticle[] = [
  {
    slug: "first-sale",
    title: "Make your first sale",
    summary: "Step-by-step from POS login to a printed receipt.",
    tags: ["onboarding", "pos", "cashier", "first sale"],
    body: `Open the POS terminal app on the cashier station. Sign in with the cashier email and PIN issued by the manager.

Once signed in, the day-open screen appears. Enter the opening cash float (the cash physically in the drawer). The drawer pops open so you can verify, then the sale screen loads.

Scan a product barcode or type into the search box. The line appears in the cart on the right with quantity 1 and the live tax breakdown.

Tap Checkout. Pick a payment method, enter the amount tendered if cash, and tap Process. The receipt prints automatically and the sale is queued for FBR submission in the background.`,
  },
  {
    slug: "day-open",
    title: "Open the day",
    summary: "What the opening float is and why it matters.",
    tags: ["day open", "cash drawer", "float"],
    body: `Every shift starts with day-open. The cashier enters how much cash is in the drawer at the start of the shift — the "opening float". The system uses this number plus the cash payments during the shift to compute the expected drawer balance at day-close.

If the actual count at day-close differs from the expected balance, the variance is logged. Persistent variances are visible to the owner in the cashier-performance report.`,
  },
  {
    slug: "day-close",
    title: "Close the day",
    summary: "Counting out, recording variance, and printing the Z-report.",
    tags: ["day close", "z report", "cash"],
    body: `At end of shift, tap Close day. The screen shows the expected drawer total based on the opening float and recorded cash payments.

Count the physical cash and enter the counted total. The variance line shows how far off you are. Add a note if the variance is non-zero.

Tap Close day to finalize. The Z-report prints. Hand the cash and the printout to the owner.`,
  },
  {
    slug: "fbr-setup",
    title: "Set up FBR / PRAL integration",
    summary: "Get your taxpayer onboarded so invoices submit automatically.",
    tags: ["fbr", "pral", "compliance", "tax"],
    body: `Open Settings → FBR. Enter the production token and STRN issued by FBR for your taxpayer. The system stores tokens encrypted at rest.

Run through the sandbox scenario tests first. Each scenario exercises a different invoice shape (registered vs unregistered buyer, multiple tax rates, etc). All scenarios must succeed before the production token is accepted.

In production, every sale is submitted automatically. The receipt re-prints with the FBR invoice number once PRAL responds. Failures retry with backoff and surface in the FBR submissions report.`,
  },
  {
    slug: "returns",
    title: "Process a return",
    summary: "Within 72 hours vs after — and what changes.",
    tags: ["returns", "refund", "credit note", "amend"],
    body: `On the POS, tap Return on the sale screen. Search by local invoice number or FBR number to find the original.

Pick the lines and quantities being returned, choose a reason, and pick the refund method (cash, store credit, card reversal, etc).

If the original sale is within 72 hours of submission, the return is processed as an FBR amendment — it consumes a slice of your monthly cancel budget (10% of last month sales).

After 72 hours, the return becomes a credit note: a separate FBR invoice that references the original. Credit notes do not consume the budget.

Damaged or expired items do not return to stock; wrong-item or changed-mind returns do.`,
  },
  {
    slug: "csv-import",
    title: "Import a product catalog",
    summary: "Bulk-load your products from a spreadsheet.",
    tags: ["catalog", "products", "csv", "import"],
    body: `Open Catalog → Products → Import. Download the template CSV. Fill in one row per product with SKU, name, category, UoM, cost price, sale price, tax rate, and HS code.

Upload the file. The importer validates every row before committing — you will see a per-row error list if anything is off.

A successful import creates the products with stock level 0 across all branches. Use Inventory → Adjustments to set opening balances.`,
  },
  {
    slug: "cancel-budget",
    title: "Cancel budget — what is the 10% rule?",
    summary: "How FBR limits how much you can amend or cancel each month.",
    tags: ["fbr", "cancel", "amend", "budget", "compliance"],
    body: `FBR allows a taxpayer to amend or cancel up to 10% of the previous month's gross sales each calendar month. Once consumed, the only way to fix an invoice is a credit note (which is its own separate FBR submission).

The system tracks consumption automatically. Every successful amend or cancel deducts the invoice grand total from the remaining budget. Settings → FBR → Cancel budget shows the current month status.

The budget recomputes on the 1st of each month at 00:05 PKT, based on the previous month's qualifying invoices.`,
  },
  {
    slug: "offline-mode",
    title: "Why is the sync indicator red?",
    summary: "What happens when the terminal cannot reach the server.",
    tags: ["sync", "offline", "outage"],
    body: `The sync indicator in the top corner of the POS shows three states:

Green — connected and up to date.
Amber — queued items waiting to sync (network is slow or briefly down).
Red — sync has been failing for more than 60 seconds.

Even with a red indicator, sales continue. The terminal keeps a local SQLite database; every sale is written there first and queued for the server. When connectivity comes back, the queue drains automatically.

If the indicator stays red for hours, check that the server is reachable from the shop network and that the cashier is signed in.`,
  },
];
