import { CheckCircle2, Circle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useActivateProductionToken,
  useFbrStatus,
  useSubmitSandboxToken,
} from "@/lib/queries";

const STEPS = [
  { n: 1, title: "Confirm IRIS account", body: "Make sure you've logged into FBR's IRIS portal at least once." },
  { n: 2, title: "Choose integrator", body: "PRAL is free and recommended. Other licensed integrators charge per-invoice." },
  { n: 3, title: "Business nature & sector", body: "Edit your tenant profile (business_natures + fbr_sector) — admin → Settings (Phase 5)." },
  { n: 4, title: "Technical contact", body: "Submitted to PRAL via the IRIS portal manually." },
  { n: 5, title: "IP whitelisting", body: "We declare our static IPs to PRAL. Tracked under FBR → IP whitelist." },
  { n: 6, title: "Sandbox token", body: "Paste the sandbox token from IRIS below." },
];

export default function FbrSetupWizard() {
  const { data: status } = useFbrStatus();
  const submitSandbox = useSubmitSandboxToken();
  const activateProd = useActivateProductionToken();

  const [sandboxToken, setSandboxToken] = useState("");
  const [prodToken, setProdToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmitSandbox(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await submitSandbox.mutateAsync({ token: sandboxToken });
      setSandboxToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  async function onActivateProd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await activateProd.mutateAsync({ token: prodToken });
      setProdToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">FBR / PRAL setup</h1>
        <p className="text-sm text-muted-foreground">
          Walk through the 6 steps to activate FBR digital invoicing.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Steps</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {STEPS.map((s) => {
              const done = (
                (s.n === 6 && !!status?.sandbox?.has_token) ||
                (s.n < 6 /* manual steps; mark as done in V1 */)
              );
              return (
                <li key={s.n} className="flex items-start gap-3 text-sm">
                  {done ? (
                    <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-700" />
                  ) : (
                    <Circle className="mt-0.5 h-5 w-5 text-muted-foreground/40" />
                  )}
                  <div>
                    <div className="font-medium">{s.n}. {s.title}</div>
                    <div className="text-muted-foreground">{s.body}</div>
                  </div>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Sandbox token</CardTitle>
          <CardDescription>
            Paste the token from IRIS once your IPs are whitelisted.
            {status?.sandbox?.has_token && (
              <span className="ml-1 text-green-700">Already configured.</span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmitSandbox} className="grid grid-cols-3 gap-3">
            <div className="col-span-3">
              <Label htmlFor="sb">Token</Label>
              <Input
                id="sb"
                type="password"
                value={sandboxToken}
                onChange={(e) => setSandboxToken(e.target.value)}
                placeholder="paste sandbox token here"
              />
            </div>
            <Button type="submit" disabled={!sandboxToken || submitSandbox.isPending}>
              {submitSandbox.isPending ? "Saving…" : "Save sandbox token"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Production token</CardTitle>
          <CardDescription>
            Activate production once all eligible scenarios pass.{" "}
            <Link to="/fbr/scenarios" className="underline-offset-2 hover:underline">
              Run scenarios →
            </Link>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!status?.all_scenarios_passed ? (
            <p className="text-sm text-amber-700">
              Production activation is locked until every eligible scenario reports{" "}
              <strong>success</strong>. Status: {status?.passed_scenarios.length ?? 0} passed
              / {status?.eligible_scenarios.length ?? 0} eligible.
            </p>
          ) : status?.production?.has_token ? (
            <p className="text-sm text-green-700">
              Production is active. Submissions go to live FBR.
            </p>
          ) : (
            <form onSubmit={onActivateProd} className="grid grid-cols-3 gap-3">
              <div className="col-span-3">
                <Label htmlFor="pr">Production token</Label>
                <Input
                  id="pr"
                  type="password"
                  value={prodToken}
                  onChange={(e) => setProdToken(e.target.value)}
                  placeholder="paste production token here"
                />
              </div>
              <Button type="submit" disabled={!prodToken || activateProd.isPending}>
                {activateProd.isPending ? "Activating…" : "Activate production"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
