/**
 * Settings → Business profile (read-only).
 *
 * Shows the tenant what their account is configured as: business
 * mode (POS / Digital Invoicing), FBR business nature(s), sector.
 * Editing these values is a platform-admin operation — the super-
 * admin sets them when the tenant is provisioned, based on which
 * product the customer signed up for:
 *
 *   - "POS / IMS" tenants → counter-side terminal + inventory +
 *     hardware (mandatory for Tier-1 retailers per STGO 17/2022)
 *   - "Digital Invoicing" tenants → back-office invoicing only
 *     (service providers, wholesalers, marriage halls, etc.)
 *
 * Two products, two pre-shaped experiences. The tenant operator
 * never has to think about modules.
 *
 * If a tenant needs to switch products (e.g. they opened a counter
 * shop after starting as digital-only), they contact support and
 * the super-admin re-provisions them.
 */

import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTenantSetup, type BusinessMode } from "@/lib/queries";

const MODE_LABELS: Record<BusinessMode, string> = {
  pos: "POS / IMS (counter-side)",
  digital_invoicing: "Digital Invoicing (back-office)",
  both: "POS + Digital Invoicing",
};

const MODE_BLURB: Record<BusinessMode, string> = {
  pos:
    "Counter-side POS for shops with a cashier and till. Includes "
    + "inventory, hardware support, terminals, and customer display. "
    + "Required for Tier-1 retailers under FBRIMS / STGO 17/2022.",
  digital_invoicing:
    "Back-office invoicing for businesses that don't run a counter — "
    + "service providers, wholesalers, marriage halls, importers, "
    + "exporters. Invoices are composed at a desk and submitted to "
    + "FBR's Digital Invoicing system.",
  both:
    "Hybrid setup. Both surfaces enabled. Used for businesses that "
    + "operate a counter AND issue back-office invoices.",
};

export default function BusinessProfileRoute() {
  const { data, isLoading } = useTenantSetup();

  if (isLoading || !data) {
    return (
      <p className="p-6 text-sm text-muted-foreground">Loading business profile…</p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <Link to="/settings" className="text-sm text-muted-foreground hover:underline">
          ← Settings
        </Link>
        <div className="mt-1 flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Business profile</h1>
          <Badge variant="info">{data.business_name}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          How your account is set up. Need to change product type
          (POS ↔ Digital Invoicing)? Contact support and we'll
          re-provision your account.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Product type</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          <div className="text-base font-medium">
            {MODE_LABELS[data.business_mode]}
          </div>
          <p className="text-sm text-muted-foreground">
            {MODE_BLURB[data.business_mode]}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">FBR business nature</CardTitle>
        </CardHeader>
        <CardContent>
          {data.fbr_business_natures.length === 0 ? (
            <p className="text-sm text-muted-foreground">— Not set —</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {data.fbr_business_natures.map((n) => (
                <Badge key={n} variant="info">{n}</Badge>
              ))}
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            FBR uses this taxonomy to validate which invoice scenarios
            apply to your business.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">FBR sector</CardTitle>
        </CardHeader>
        <CardContent>
          {data.fbr_sector ? (
            <Badge variant="info">{data.fbr_sector}</Badge>
          ) : (
            <p className="text-sm text-muted-foreground">— Not set —</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">NTN</CardTitle>
        </CardHeader>
        <CardContent>
          <code className="rounded bg-muted px-2 py-1 text-sm">{data.ntn}</code>
        </CardContent>
      </Card>
    </div>
  );
}
