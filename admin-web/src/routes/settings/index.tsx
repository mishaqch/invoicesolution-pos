import {
  Activity,
  Briefcase,
  Building2,
  ChevronRight,
  CreditCard,
  FileText,
  HelpCircle,
  Receipt,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useModules, type ModuleKey } from "@/features/modules/hooks";

interface SettingTile {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  description: string;
  to: string;
  /** Hide this tile when the named module isn't enabled for the
   *  tenant. Tiles without `module` are always visible (Business
   *  profile, Payment methods, FBR/PRAL, Help). */
  module?: ModuleKey;
}

const TILES: SettingTile[] = [
  {
    icon: Briefcase,
    label: "Business profile",
    description:
      "View your account setup — product type (POS / Digital Invoicing) "
      + "and FBR taxonomy. Changes are handled by support.",
    to: "/settings/business-profile",
  },
  {
    icon: Building2,
    label: "Branches & terminals",
    description: "Manage shop locations and the POS terminals at each one.",
    to: "/branches",
    module: "branches",
  },
  {
    icon: CreditCard,
    label: "Payment methods",
    description: "Enable / disable cash, card, wallet, cheque, credit, store credit.",
    to: "/payments/settings",
  },
  {
    icon: Receipt,
    label: "Cheques",
    description: "Track issued and received cheques through clearance.",
    to: "/payments/cheques",
    module: "payments_advanced",
  },
  {
    icon: FileText,
    label: "FBR / PRAL",
    description: "Tokens, scenario tests, cancel-budget, manual amendments.",
    to: "/fbr",
    module: "fbr",
  },
  {
    icon: Activity,
    label: "Sync health",
    description: "Per-terminal sync status and queued event counts.",
    to: "/sync",
    module: "terminals",
  },
  {
    icon: Wrench,
    label: "Hardware",
    description: "Per-station bring-up checklist for drawer, printer, scale, scanner.",
    to: "/settings/hardware",
    module: "hardware",
  },
  {
    icon: HelpCircle,
    label: "Help center",
    description: "FAQ and how-to articles for common workflows.",
    to: "/help",
  },
];

export default function SettingsIndex() {
  const { data: modules } = useModules();
  const enabled = modules?.enabled;

  const visibleTiles = TILES.filter(
    (t) => !t.module || !enabled || enabled.includes(t.module),
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure your business, integrations, and devices.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {visibleTiles.map((t) => {
          const Icon = t.icon;
          return (
            <Link key={t.to} to={t.to} className="group block">
              <Card className="h-full transition-colors hover:bg-accent">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Icon className="h-4 w-4" aria-hidden /> {t.label}
                    </span>
                    <ChevronRight className="h-4 w-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-muted-foreground">
                  {t.description}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
