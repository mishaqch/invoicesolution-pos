import { CheckCircle2, FileText, Gauge } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useFbrCancelBudget, useFbrStatus } from "@/lib/queries";

export default function FbrDashboard() {
  const { data: status } = useFbrStatus();
  const { data: budget } = useFbrCancelBudget();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">FBR / Compliance</h1>

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
    </div>
  );
}
