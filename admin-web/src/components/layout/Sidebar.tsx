import {
  Activity,
  BarChart3,
  AlertTriangle,
  Boxes,
  Building2,
  CalendarClock,
  ChefHat,
  Grid3x3,
  LayoutGrid,
  Monitor,
  ClipboardList,
  Utensils,
  FileText,
  HelpCircle,
  LayoutDashboard,
  Package,
  PackagePlus,
  Receipt,
  Settings,
  ShoppingCart,
  Truck,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { useModules, type ModuleKey, type Vertical } from "@/features/modules/hooks";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { useSidebarStore } from "@/stores/sidebar";

interface Item {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  end?: boolean;
  /** When set, the item is hidden if this module is not enabled for
   *  the tenant. Items without `module` are always visible
   *  (Dashboard, Help, Settings). */
  module?: ModuleKey;
  /** When set, the item only shows for tenants of this vertical
   *  (e.g. pharmacy-only Expiry / Suppliers). Items without `vertical`
   *  show for every vertical. */
  vertical?: Vertical;
  /** When set, the item is HIDDEN for tenants of these verticals (e.g. the
   *  warehouse-style inventory tools don't fit a restaurant). */
  hideForVerticals?: Vertical[];
}

const TOP: Item[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  // Invoices are the central artifact of the product. "Sales" was
  // ambiguous (could mean transactions, the act of selling, or a
  // metric); the FBR Digital Invoicing product specifically tracks
  // invoices, so we name the nav item after the artifact.
  { to: "/sales", label: "Invoices", icon: Receipt, end: true, module: "sales" },
  { to: "/sales/new", label: "New invoice", icon: ShoppingCart, module: "sales" },
  // Held invoices are a counter-side concept (cashier parks a half-rung
  // sale, recalls it later). Digital-invoicing tenants compose invoices
  // at a desk and never "park" them, so gate on `terminals`.
  { to: "/sales/held", label: "Held invoices", icon: ShoppingCart, module: "terminals" },
  { to: "/returns", label: "Returns", icon: ShoppingCart, end: true, module: "returns" },
];

// Catalog primitives. DI tenants (service providers, wholesalers) also
// need products — every FBR invoice line carries an HS code, even for
// services (typically 9802.9000). What differs:
//   - "Tax rates" is a POS-only concept (per-SKU rate overrides). DI
//     tenants pick a single sector-wide rate during setup and stick to
//     it. Hidden via `terminals` module.
//   - The catalog row is "Products" for everyone except restaurants
//     (which see "Menu" — see withVerticalLabels).
const CATALOG: Item[] = [
  { to: "/catalog/products", label: "Products", icon: Package },
  { to: "/catalog/categories", label: "Categories", icon: Boxes },
  { to: "/catalog/tax-rates", label: "Tax rates", icon: FileText, module: "terminals" },
  { to: "/catalog/hs-codes", label: "HS codes", icon: FileText },
];

// Warehouse-style stock management (grocery + pharmacy). Restaurants think in
// orders/KOTs, not stock ledgers, so the whole group is hidden for them
// (hideForVerticals: ["restaurant"]) — except the pharmacy-only items which
// already gate to pharmacy.
const INVENTORY: Item[] = [
  { to: "/inventory/stock", label: "Stock by branch", icon: Boxes, module: "inventory", hideForVerticals: ["restaurant"] },
  { to: "/inventory/restock", label: "Restock", icon: AlertTriangle, module: "inventory", hideForVerticals: ["restaurant"] },
  // Pharmacy-only: batches at/near expiry. Hidden for grocery tenants.
  { to: "/inventory/expiry", label: "Expiry", icon: CalendarClock, module: "inventory", vertical: "pharmacy" },
  { to: "/inventory/movements", label: "Movements", icon: ClipboardList, module: "inventory", hideForVerticals: ["restaurant"] },
  { to: "/inventory/adjustments", label: "Adjustments", icon: ClipboardList, module: "inventory", hideForVerticals: ["restaurant"] },
  { to: "/inventory/transfers", label: "Transfers", icon: ClipboardList, module: "inventory", hideForVerticals: ["restaurant"] },
  { to: "/inventory/audits", label: "Audits", icon: ClipboardList, module: "inventory", hideForVerticals: ["restaurant"] },
  // Procurement (pharmacy-only): suppliers + receiving stock via goods receipts.
  { to: "/purchases/receive", label: "Receive stock", icon: PackagePlus, module: "inventory", vertical: "pharmacy" },
  { to: "/suppliers", label: "Suppliers", icon: Truck, module: "inventory", vertical: "pharmacy" },
];

// Restaurant (F&B vertical only). All gated by the restaurant module +
// vertical, so non-restaurant tenants never see this section.
const RESTAURANT: Item[] = [
  { to: "/restaurant/floor", label: "Floor", icon: LayoutGrid, module: "restaurant", vertical: "restaurant" },
  { to: "/restaurant/kitchen", label: "Kitchen", icon: ChefHat, module: "restaurant", vertical: "restaurant" },
  { to: "/restaurant/tables", label: "Tables", icon: Grid3x3, module: "restaurant", vertical: "restaurant" },
  { to: "/restaurant/modifiers", label: "Modifiers", icon: Utensils, module: "restaurant", vertical: "restaurant" },
];

const ADMIN: Item[] = [
  { to: "/branches", label: "Branches", icon: Building2, module: "branches" },
  { to: "/terminals", label: "Terminals", icon: Monitor, module: "terminals" },
  // Sync health is a terminal-fleet dashboard. DI tenants don't run
  // terminals, so hide the panel — the green/amber/red traffic light
  // they'd see would always read green-with-no-data and just be noise.
  { to: "/sync", label: "Sync health", icon: Activity, end: true, module: "terminals" },
  { to: "/payments/settings", label: "Payment methods", icon: FileText },
  { to: "/payments/cheques", label: "Cheques", icon: FileText, module: "payments_advanced" },
  { to: "/customers", label: "Customers", icon: Users, end: true, module: "customers" },
  { to: "/reports", label: "Reports", icon: BarChart3, module: "reports_basic" },
  { to: "/fbr", label: "FBR", icon: FileText, end: true, module: "fbr" },
  { to: "/settings/hardware", label: "Hardware", icon: Wrench, module: "hardware" },
  { to: "/help", label: "Help", icon: HelpCircle },
  { to: "/settings", label: "Settings", icon: Settings, end: true },
];

export function Sidebar() {
  // useModules() drives which items render. While the request is in
  // flight we show everything (the hook returns true on isLoading) so
  // operators don't see the menu pop in.
  const { data: modules } = useModules();
  const enabled = modules?.enabled;
  const vertical = modules?.vertical;

  function visible(items: Item[]): Item[] {
    if (!enabled) return items;
    return items.filter(
      (it) =>
        (!it.module || enabled.includes(it.module)) &&
        // Hide vertical-specific links for other verticals. While the vertical
        // is still loading we keep the item (show-too-much-briefly), matching
        // the module behaviour above.
        (!it.vertical || !vertical || it.vertical === vertical) &&
        // Hide items that don't fit this vertical (e.g. warehouse inventory for
        // a restaurant). Only hide once we know the vertical.
        (!it.hideForVerticals || !vertical || !it.hideForVerticals.includes(vertical)),
    );
  }

  // A restaurant's "products" are menu items — relabel for the right language.
  // (Digital-Invoicing tenants keep "Products" — the catalog row is always
  // "Products" except for restaurants, which see "Menu".)
  function withVerticalLabels(items: Item[]): Item[] {
    if (vertical !== "restaurant") return items;
    return items.map((it) =>
      it.to === "/catalog/products" ? { ...it, label: "Menu" } : it,
    );
  }

  const top = visible(TOP);
  const catalog = withVerticalLabels(visible(CATALOG));
  const inventory = visible(INVENTORY);
  const restaurant = visible(RESTAURANT);
  const adminItems = visible(ADMIN);

  const open = useSidebarStore((s) => s.open);
  const close = useSidebarStore((s) => s.close);

  // Close the drawer on Escape, and whenever the viewport grows to desktop
  // (md+) where the sidebar is inline — so it can't get stuck open after a
  // rotate/resize. Also lock body scroll while the drawer is open on mobile.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => { if (mq.matches) close(); };
    window.addEventListener("keydown", onKey);
    mq.addEventListener("change", onChange);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      mq.removeEventListener("change", onChange);
      document.body.style.overflow = "";
    };
  }, [open, close]);

  // The nav content is identical on desktop and in the mobile drawer.
  const content = (
    <div className="flex h-full flex-col">
      <BrandStrip />
      <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3 [scrollbar-width:thin]">
        {top.length > 0 && <Group items={top} />}
        {catalog.length > 0 && <Section title="Catalog" items={catalog} />}
        {inventory.length > 0 && <Section title="Inventory" items={inventory} />}
        {restaurant.length > 0 && <Section title="Restaurant" items={restaurant} />}
        {adminItems.length > 0 && <Section title="Admin" items={adminItems} />}
      </nav>
      <div className="border-t px-4 py-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          FBR-compliant build
        </span>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: inline fixed-width sidebar (unchanged). */}
      <aside className="hidden border-r bg-card md:block md:w-60">{content}</aside>

      {/* Mobile: slide-in drawer + dim backdrop, shown only below md when open. */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity md:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={close}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 max-w-[80vw] border-r bg-card shadow-xl transition-transform duration-200 md:hidden",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        role="dialog"
        aria-label="Navigation"
        aria-modal="true"
      >
        <button
          type="button"
          onClick={close}
          aria-label="Close navigation"
          className="absolute right-2 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
        >
          <X className="h-4 w-4" />
        </button>
        {content}
      </aside>
    </>
  );
}

function BrandStrip() {
  // Pull tenant from the auth store so the chrome reflects the logged-in
  // tenant's identity (their store name + uploaded logo) instead of the
  // hardcoded product name. Falls back to "POS System" / Receipt icon
  // before /auth/me has resolved or for users without a tenant.
  const tenant = useAuthStore((s) => s.tenant);
  const [logoBroken, setLogoBroken] = useState(false);

  const hasLogo = Boolean(tenant?.logo_url) && !logoBroken;
  const initial = (tenant?.business_name ?? "P").charAt(0).toUpperCase();
  const label = tenant?.business_name ?? "POS System";

  return (
    <div className="flex items-center gap-2.5 border-b px-4 py-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-primary text-primary-foreground shadow-sm">
        {hasLogo ? (
          <img
            src={tenant!.logo_url!}
            alt=""
            className="h-full w-full object-cover"
            // If the URL 404s or the host blocks hotlinking, drop back
            // to the monogram so we don't render a broken-image icon.
            onError={() => setLogoBroken(true)}
          />
        ) : tenant ? (
          <span className="text-xs font-bold leading-none">{initial}</span>
        ) : (
          <Receipt className="h-4 w-4" aria-hidden />
        )}
      </div>
      <div className="flex min-w-0 flex-col leading-tight">
        <span
          className="truncate text-sm font-semibold tracking-tight"
          title={label}
        >
          {label}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Admin
        </span>
      </div>
    </div>
  );
}

function Section({ title, items }: { title: string; items: Item[] }) {
  return (
    <div>
      <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        {title}
      </div>
      <Group items={items} />
    </div>
  );
}

function Group({ items }: { items: Item[] }) {
  const closeDrawer = useSidebarStore((s) => s.close);
  return (
    <div className="space-y-0.5">
      {items.map(({ to, label, icon: Icon, disabled, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150",
              disabled
                ? "cursor-not-allowed text-muted-foreground/60"
                : isActive
                  // Active: brand-tinted background + emerald ink + left accent bar
                  ? "bg-primary-soft text-primary-soft-foreground"
                  : "text-foreground/70 hover:bg-accent hover:text-accent-foreground",
            )
          }
          // Disabled links are inert; live links also dismiss the mobile drawer.
          onClick={disabled ? (e) => e.preventDefault() : () => closeDrawer()}
          aria-disabled={disabled}
          title={disabled ? "Coming in a later phase" : undefined}
        >
          {({ isActive }) => (
            <>
              {/* Active accent bar on the left edge — brand emphasis */}
              {isActive && (
                <span
                  aria-hidden
                  className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </div>
  );
}
