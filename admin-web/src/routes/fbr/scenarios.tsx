import { CheckCircle2, Loader2, Play, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useFbrScenarios,
  useFbrStatus,
  useRunScenarios,
  type FbrScenarioRow,
} from "@/lib/queries";

function ScenarioStatus({ row }: { row: FbrScenarioRow }) {
  if (row.status === "success") return <Badge variant="default">Success</Badge>;
  if (row.status === "failed") return <Badge variant="destructive">Failed</Badge>;
  if (row.status === "submitting") return <Badge variant="outline">Running…</Badge>;
  return <Badge variant="outline">Pending</Badge>;
}

export default function ScenariosPage() {
  const { data: status } = useFbrStatus();
  const { data: scenarios } = useFbrScenarios();
  const runAll = useRunScenarios();

  const eligible = status?.eligible_scenarios ?? [];
  const byCode = new Map(scenarios?.results.map((r) => [r.scenario_code, r]) ?? []);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sandbox scenarios</h1>
          <p className="text-sm text-muted-foreground">
            Each scenario submits a synthetic invoice to PRAL's sandbox and
            reports the result. All eligible scenarios must pass before
            production activation.
          </p>
        </div>
        <Button
          onClick={() => runAll.mutate()}
          disabled={runAll.isPending || !status?.sandbox?.has_token}
        >
          {runAll.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Run all eligible
        </Button>
      </div>

      {!status?.sandbox?.has_token && (
        <p className="text-sm text-amber-700">
          A sandbox token is required first. Paste yours under FBR → Setup.
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {eligible.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No eligible scenarios for your sector yet.
          </p>
        ) : (
          eligible.map((s) => {
            const row = byCode.get(s.code);
            return (
              <Card key={s.code}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{s.code}</CardTitle>
                    {row ? <ScenarioStatus row={row} /> : <Badge variant="outline">Pending</Badge>}
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p className="text-muted-foreground">{s.description}</p>
                  {row?.fbr_invoice_number && (
                    <div className="text-xs">
                      <span className="text-muted-foreground">FBR #</span>{" "}
                      <span className="font-mono">{row.fbr_invoice_number}</span>
                    </div>
                  )}
                  {row?.error_message && (
                    <div className="rounded bg-red-50 p-2 text-xs text-red-900">
                      <XCircle className="mr-1 inline h-3 w-3" />
                      {row.error_message}
                    </div>
                  )}
                  {row?.last_attempt_at && (
                    <div className="text-xs text-muted-foreground">
                      Last attempt: {new Date(row.last_attempt_at).toLocaleString()}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {status?.all_scenarios_passed && (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
          <CheckCircle2 className="mr-1 inline h-4 w-4" />
          All scenarios passed. You can activate production from FBR → Setup.
        </div>
      )}
    </div>
  );
}
