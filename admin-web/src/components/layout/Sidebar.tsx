import {
  BarChart3,
  Boxes,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Package,
  Settings,
  ShoppingCart,
  Truck,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

interface Item {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
}

const ITEMS: Item[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sales", label: "Sales", icon: ShoppingCart, disabled: true },
  { to: "/inventory", label: "Inventory", icon: Boxes, disabled: true },
  { to: "/catalog", label: "Catalog", icon: Package, disabled: true },
  { to: "/customers", label: "Customers", icon: Users, disabled: true },
  { to: "/suppliers", label: "Suppliers", icon: Truck, disabled: true },
  { to: "/reports", label: "Reports", icon: BarChart3, disabled: true },
  { to: "/fbr", label: "FBR", icon: FileText, disabled: true },
  { to: "/audit", label: "Audit", icon: ClipboardList, disabled: true },
  { to: "/settings", label: "Settings", icon: Settings, disabled: true },
];

export function Sidebar() {
  return (
    <aside className="hidden border-r bg-muted/40 md:block md:w-60">
      <div className="flex h-full flex-col">
        <div className="border-b px-4 py-4 text-sm font-semibold tracking-tight">
          Pakistan POS
        </div>
        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {ITEMS.map(({ to, label, icon: Icon, disabled }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
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
        </nav>
        <div className="border-t px-4 py-3 text-xs text-muted-foreground">
          Phase 0 build
        </div>
      </div>
    </aside>
  );
}
