import { CheckCircle2, FileText, Gauge, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useIsImsSdc } from "@/features/modules/hooks";
import { useFbrCancelBudget, useFbrPosStatus, useFbrStatus } from "@/lib/queries";

export default function FbrDashboard() {
  const imsSdc = useIsImsSdc();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">FBR / Compliance</h1>
      {imsSdc ? <ImsDashboard /> : <DiApiDashboard />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* IMS / SDC tenants: no DI-API token, no sandbox scenarios. Show the  */
/* per-branch fiscalization-service connection status instead.         */
/* ------------------------------------------------------------------ */
function ImsDashboard() {
  const { data: pos } = useFbrPosStatus();
  const { data: budget } = useFbrCancelBudget();
  const branches = pos?.branches ?? [];
  const registered = branches.filter((b) => b.registered).length;

  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              <ShieldCheck className="mr-1 inline h-4 w-4" /> FBR Fiscalization (IMS)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-lg">{registered} / {branches.length}</span>
            <p className="mt-1 text-xs text-muted-foreground">
              branches with an FBR POS ID configured. Invoices fiscalize through
              the FBR Fiscalization service running at each counter.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              <Gauge className="mr-1 inline h-4 w-4" /> Cancel budget
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-lg">
              Rs {budget ? parseFloat(budget.remaining_amount).toFixed(0) : "—"}
            </div>
            <Link to="/fbr/cancel-budget" className="mt-2 inline-block text-xs underline-offset-2 hover:underline">
              View tracker →
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm">Quick links</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Link to="/branches" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Branch FBR POS IDs
            </Link>
            <Link to="/fbr/submissions" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Submission log
            </Link>
            <Link to="/fbr/cancel-budget" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Cancel budget
            </Link>
            <Link to="/fbr/manual-amendment" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Manual amendment
            </Link>
          </CardContent>
        </Card>
      </div>

      {branches.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Branch fiscalization status</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {branches.map((b) => (
              <div key={b.branch_id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                <span className="font-medium">{b.branch_name}</span>
                <span className="flex items-center gap-3">
                  <span className="font-mono text-xs text-muted-foreground">
                    {b.fbr_pos_id ? `POS ${b.fbr_pos_id}` : "No POS ID"}
                  </span>
                  {b.connected ? (
                    <Badge variant="success">Connected</Badge>
                  ) : b.registered ? (
                    <Badge variant="secondary">Registered</Badge>
                  ) : (
                    <Badge variant="outline">Not set</Badge>
                  )}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/* DI-API tenants: PRAL token environment + sandbox scenarios.         */
/* (Unchanged from the original dashboard.)                            */
/* ------------------------------------------------------------------ */
function DiApiDashboard() {
  const { data: status } = useFbrStatus();
  const { data: budget } = useFbrCancelBudget();

  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Environment</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge
              variant={
                status?.environment === "production" ? "default"
                : status?.environment === "sandbox" ? "secondary"
                : "outline"
              }
            >
              {status?.environment ?? "—"}
            </Badge>
            <p className="mt-2 text-xs text-muted-foreground">
              {status?.last_successful_submission_at
                ? `Last success: ${new Date(status.last_successful_submission_at).toLocaleString()}`
                : "No successful submissions yet."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Scenarios</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {status?.all_scenarios_passed && (
                <CheckCircle2 className="h-4 w-4 text-green-700" />
              )}
              <span className="font-mono text-lg">
                {status?.passed_scenarios.length ?? 0} /{" "}
                {status?.eligible_scenarios.length ?? 0}
              </span>
            </div>
            <Link to="/fbr/scenarios" className="mt-2 inline-block text-xs underline-offset-2 hover:underline">
              Run sandbox tests →
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              <Gauge className="mr-1 inline h-4 w-4" />
              Cancel budget
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-lg">
              Rs {budget ? parseFloat(budget.remaining_amount).toFixed(0) : "—"}
            </div>
            <Link to="/fbr/cancel-budget" className="mt-2 inline-block text-xs underline-offset-2 hover:underline">
              View tracker →
            </Link>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-sm">Quick links</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Link to="/fbr/setup" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Setup wizard
            </Link>
            <Link to="/fbr/scenarios" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Scenario tests
            </Link>
            <Link to="/fbr/submissions" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Submission log
            </Link>
            <Link to="/fbr/cancel-budget" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Cancel budget
            </Link>
            <Link to="/fbr/manual-amendment" className="block hover:underline">
              <FileText className="mr-1 inline h-4 w-4" /> Manual amendment
            </Link>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
