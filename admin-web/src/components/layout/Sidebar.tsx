import {
  BarChart3,
  Boxes,
  Building2,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Package,
  Settings,
  ShoppingCart,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

interface Item {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  end?: boolean;
}

const TOP: Item[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/sales", label: "Sales", icon: ShoppingCart, disabled: true },
];

const CATALOG: Item[] = [
  { to: "/catalog/products", label: "Products", icon: Package },
  { to: "/catalog/categories", label: "Categories", icon: Boxes },
  { to: "/catalog/tax-rates", label: "Tax rates", icon: FileText },
  { to: "/catalog/hs-codes", label: "HS codes", icon: FileText },
];

const INVENTORY: Item[] = [
  { to: "/inventory/stock", label: "Stock by branch", icon: Boxes },
  { to: "/inventory/movements", label: "Movements", icon: ClipboardList },
  { to: "/inventory/adjustments", label: "Adjustments", icon: ClipboardList },
];

const ADMIN: Item[] = [
  { to: "/branches", label: "Branches", icon: Building2 },
  { to: "/customers", label: "Customers", icon: Users, disabled: true },
  { to: "/reports", label: "Reports", icon: BarChart3, disabled: true },
  { to: "/fbr", label: "FBR", icon: FileText, disabled: true },
  { to: "/settings", label: "Settings", icon: Settings, disabled: true },
];

export function Sidebar() {
  return (
    <aside className="hidden border-r bg-muted/40 md:block md:w-60">
      <div className="flex h-full flex-col">
        <div className="border-b px-4 py-4 text-sm font-semibold tracking-tight">
          Pakistan POS
        </div>
        <nav className="flex-1 space-y-3 px-2 py-3">
          <Group items={TOP} />
          <Section title="Catalog" items={CATALOG} />
          <Section title="Inventory" items={INVENTORY} />
          <Section title="Admin" items={ADMIN} />
        </nav>
        <div className="border-t px-4 py-3 text-xs text-muted-foreground">
          Phase 1 build
        </div>
      </div>
    </aside>
  );
}

function Section({ title, items }: { title: string; items: Item[] }) {
  return (
    <div>
      <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80">
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
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              disabled
                ? "cursor-not-allowed text-muted-foreground/60"
                : isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
          onClick={disabled ? (e) => e.preventDefault() : undefined}
          aria-disabled={disabled}
          title={disabled ? "Coming in a later phase" : undefined}
        >
          <Icon className="h-4 w-4" />
          <span>{label}</span>
        </NavLink>
      ))}
    </div>
  );
}
