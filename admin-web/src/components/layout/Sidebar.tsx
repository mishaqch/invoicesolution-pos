import {
  Activity,
  BarChart3,
  Boxes,
  Building2,
  ClipboardList,
  FileText,
  HelpCircle,
  LayoutDashboard,
  Package,
  Receipt,
  Settings,
  ShoppingCart,
  Users,
  Wrench,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useModules, type ModuleKey } from "@/features/modules/hooks";
import { cn } from "@/lib/utils";

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
}

const TOP: Item[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/sales", label: "Invoices", icon: Receipt, end: true, module: "sales" },
  { to: "/sales/new", label: "New sale", icon: ShoppingCart, module: "sales" },
  { to: "/sales/held", label: "Held sales", icon: ShoppingCart, module: "sales" },
  { to: "/returns", label: "Returns", icon: ShoppingCart, end: true, module: "returns" },
];

// Products / categories / tax rates / HS codes are catalog primitives —
// they don't have a dedicated module in V1. They stay always-visible so
// even sales-only tenants can manage their SKUs.
const CATALOG: Item[] = [
  { to: "/catalog/products", label: "Products", icon: Package },
  { to: "/catalog/categories", label: "Categories", icon: Boxes },
  { to: "/catalog/tax-rates", label: "Tax rates", icon: FileText },
  { to: "/catalog/hs-codes", label: "HS codes", icon: FileText },
];

const INVENTORY: Item[] = [
  { to: "/inventory/stock", label: "Stock by branch", icon: Boxes, module: "inventory" },
  { to: "/inventory/movements", label: "Movements", icon: ClipboardList, module: "inventory" },
  { to: "/inventory/adjustments", label: "Adjustments", icon: ClipboardList, module: "inventory" },
  { to: "/inventory/transfers", label: "Transfers", icon: ClipboardList, module: "inventory" },
  { to: "/inventory/audits", label: "Audits", icon: ClipboardList, module: "inventory" },
];

const ADMIN: Item[] = [
  { to: "/branches", label: "Branches", icon: Building2, module: "branches" },
  { to: "/sync", label: "Sync health", icon: Activity, end: true },
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

  function visible(items: Item[]): Item[] {
    if (!enabled) return items;
    return items.filter((it) => !it.module || enabled.includes(it.module));
  }

  const top = visible(TOP);
  const catalog = visible(CATALOG);
  const inventory = visible(INVENTORY);
  const adminItems = visible(ADMIN);

  return (
    <aside className="hidden border-r bg-card md:block md:w-60">
      <div className="flex h-full flex-col">
        {/* Brand strip — emerald square logo + product name */}
        <div className="flex items-center gap-2.5 border-b px-4 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
            <Receipt className="h-4 w-4" aria-hidden />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold tracking-tight">POS System</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Admin
            </span>
          </div>
        </div>
        <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3 [scrollbar-width:thin]">
          {top.length > 0 && <Group items={top} />}
          {catalog.length > 0 && <Section title="Catalog" items={catalog} />}
          {inventory.length > 0 && <Section title="Inventory" items={inventory} />}
          {adminItems.length > 0 && <Section title="Admin" items={adminItems} />}
        </nav>
        <div className="border-t px-4 py-3 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            FBR-compliant build
          </span>
        </div>
      </div>
    </aside>
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
          onClick={disabled ? (e) => e.preventDefault() : undefined}
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
