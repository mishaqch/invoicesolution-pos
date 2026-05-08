import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/stores/auth";

export default function DashboardRoute() {
  const user = useAuthStore((s) => s.user);
  const tenant = useAuthStore((s) => s.tenant);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome{user ? `, ${user.full_name}` : ""}.
        </h1>
        <p className="text-sm text-muted-foreground">
          Signed in to {tenant?.business_name ?? "—"}.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Phase 0</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The dashboard, sales list, inventory, and reports land in later phases.
          For now, this confirms identity, tenancy, and the admin chrome are
          wired correctly.
        </CardContent>
      </Card>
    </div>
  );
}
