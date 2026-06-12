/**
 * FBR / PRAL setup wizard.
 *
 * Tenant pastes their PRAL bearer + endpoint URL for sandbox first.
 * Before save, they can hit "Test connection" — we probe PRAL's
 * /pdi/v1/uom reference endpoint, which requires auth and is cheap.
 * If PRAL returns 200, the token is good; we surface the count of
 * UoMs returned as a sanity-check signal.
 *
 * Once sandbox is configured and every eligible scenario reports
 * "passed", the production card unlocks and the tenant can paste
 * their production token (separate URL: same gw.fbr.gov.pk but the
 * client's _sb suffix is dropped at submit time by FbrClient).
 */
import { CheckCircle2, Circle, Loader2, MonitorSmartphone, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useModules } from "@/features/modules/hooks";
import {
  useActivateProductionToken,
  useFbrPosStatus,
  useFbrStatus,
  useSubmitSandboxToken,
  useTestFbrToken,
  type TestTokenResult,
} from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";

const PRAL_DEFAULT_URL = "https://gw.fbr.gov.pk";

const STEPS = [
  { n: 1, title: "Confirm IRIS account", body: "Sign in to FBR's IRIS portal at least once with your NTN." },
  { n: 2, title: "Choose integrator", body: "PRAL (free) is the default. Other licensed integrators charge per invoice." },
  { n: 3, title: "Business nature & sector", body: "Set these on your tenant profile — they drive which scenarios apply." },
  { n: 4, title: "Technical contact", body: "Submit your tech contact to PRAL via the IRIS portal." },
  { n: 5, title: "IP whitelisting", body: "PRAL whitelists our static IPs. Tracked under FBR → IP whitelist." },
  { n: 6, title: "Sandbox token", body: "Paste the sandbox token + endpoint below, click Test, then Save." },
];

export default function FbrSetupWizard() {
  const { data: status } = useFbrStatus();
  const { data: modules } = useModules();
  // "POS connections" (per-branch FBR terminal status) is a POS concept. A
  // Digital-Invoicing-only back-office tenant has no POS terminals, so hide it.
  const isDigitalOnly = modules?.business_mode === "digital_invoicing";
  const submitSandbox = useSubmitSandboxToken();
  const activateProd = useActivateProductionToken();
  const test = useTestFbrToken();

  const [sandboxEndpoint, setSandboxEndpoint] = useState(PRAL_DEFAULT_URL);
  const [sandboxToken, setSandboxToken] = useState("");
  const [sandboxTest, setSandboxTest] = useState<TestTokenResult | null>(null);
  // Success banner shown after a successful save. Local state (not
  // a toast) so the operator sees confirmation right next to the
  // button they just clicked.
  const [sandboxSaved, setSandboxSaved] = useState<string | null>(null);

  const [prodEndpoint, setProdEndpoint] = useState(PRAL_DEFAULT_URL);
  const [prodToken, setProdToken] = useState("");
  const [prodTest, setProdTest] = useState<TestTokenResult | null>(null);
  const [prodSaved, setProdSaved] = useState<string | null>(null);
  // Platform-staff-only escape hatch for tokens FBR already issued.
  const isPlatformStaff = useAuthStore((s) => !!s.user?.is_platform_staff);
  const [bypassScenarios, setBypassScenarios] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // Pre-populate endpoint fields from the saved record once the
  // /fbr/status/ call returns. Only runs while the local field
  // still holds the default URL — if the operator has already
  // started editing, we don't clobber their input.
  useEffect(() => {
    const sb = status?.sandbox?.api_endpoint;
    if (sb && sandboxEndpoint === PRAL_DEFAULT_URL) {
      setSandboxEndpoint(sb);
    }
    const pr = status?.production?.api_endpoint;
    if (pr && prodEndpoint === PRAL_DEFAULT_URL) {
      setProdEndpoint(pr);
    }
    // We deliberately omit the local field values from deps — this
    // effect should fire when the SAVED value loads, not on every
    // keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.sandbox?.api_endpoint, status?.production?.api_endpoint]);

  async function onTestSandbox() {
    setError(null);
    setSandboxTest(null);
    try {
      const r = await test.mutateAsync({
        token: sandboxToken,
        api_endpoint: sandboxEndpoint,
      });
      setSandboxTest(r);
    } catch (err) {
      setSandboxTest({
        ok: false,
        detail: err instanceof Error ? err.message : "Test failed",
      });
    }
  }

  async function onSaveSandbox(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSandboxSaved(null);
    try {
      await submitSandbox.mutateAsync({
        token: sandboxToken,
        api_endpoint: sandboxEndpoint,
      });
      setSandboxToken("");
      setSandboxTest(null);
      setSandboxSaved(
        new Date().toLocaleTimeString([], {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function onTestProd() {
    setError(null);
    setProdTest(null);
    try {
      const r = await test.mutateAsync({
        token: prodToken,
        api_endpoint: prodEndpoint,
      });
      setProdTest(r);
    } catch (err) {
      setProdTest({
        ok: false,
        detail: err instanceof Error ? err.message : "Test failed",
      });
    }
  }

  async function onActivateProd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setProdSaved(null);
    try {
      await activateProd.mutateAsync({
        token: prodToken,
        api_endpoint: prodEndpoint,
        scenarios_cleared_externally: isPlatformStaff && bypassScenarios,
      });
      setProdToken("");
      setProdTest(null);
      setProdSaved(
        new Date().toLocaleTimeString([], {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activate failed");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">FBR / PRAL setup</h1>
        <p className="text-sm text-muted-foreground">
          Connect your tenant to FBR's Digital Invoicing. Tokens are
          stored encrypted (Fernet) and never displayed back.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Steps</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {STEPS.map((s) => {
              const done =
                (s.n === 6 && !!status?.sandbox?.has_token) ||
                s.n < 6; // manual steps; mark as done in V1
              return (
                <li key={s.n} className="flex items-start gap-3 text-sm">
                  {done ? (
                    <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-700" />
                  ) : (
                    <Circle className="mt-0.5 h-5 w-5 text-muted-foreground/40" />
                  )}
                  <div>
                    <div className="font-medium">
                      {s.n}. {s.title}
                    </div>
                    <div className="text-muted-foreground">{s.body}</div>
                  </div>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      {/* =========================================================
          ELIGIBLE SCENARIOS PREVIEW
          =========================================================
          What the tenant will be asked to validate against PRAL in
          sandbox before production unlocks. Auto-derived from their
          business nature(s) + sector on the tenant profile; not
          something they pick here. We surface it ahead of time so
          there are no surprises later.
          ========================================================= */}
      {/* Production-readiness checklist.

          Source of truth changed: the list used to be auto-derived
          from (business_nature × sector). Now it's the scenarios the
          platform team configured on the tenant from the IRIS profile.
          The copy and the empty-state both reflect that — the operator
          can't fix this themselves; they ask the platform team to
          confirm their IRIS list.

          We show ALL assigned scenarios (including ones our platform
          can't run yet — they get an amber 'Not yet supported' pill),
          but the progress count only includes scenarios with builders.
          The production gate also only requires the runnable ones to
          pass; not-yet-supported is on us, not the tenant. */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            FBR sandbox scenarios for your tenant
          </CardTitle>
          <CardDescription>
            FBR assigns each Digital Invoicing tenant a specific list of
            scenarios that must pass in sandbox before production can be
            activated. The list shown here is what your IRIS profile
            says; the platform team configures it from that page when
            your tenant is set up.
            {status?.eligible_scenarios && status.eligible_scenarios.length > 0 ? (
              <>
                {" "}
                <strong>
                  {status.passed_scenarios.length} of{" "}
                  {status.eligible_scenarios.length} runnable scenarios passed
                </strong>
                {" "}so far.
              </>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!status?.assigned_scenarios || status.assigned_scenarios.length === 0 ? (
            <p className="text-sm text-amber-700">
              The platform team hasn't configured your scenarios yet.
              They appear here once your IRIS profile is reviewed and
              the assigned list is saved against your tenant. Contact
              support if you've completed the IRIS sandbox steps and
              this section is still empty.
            </p>
          ) : (
            <>
              <ul className="space-y-2">
                {status.assigned_scenarios.map((s) => {
                  const passed = status.passed_scenarios.includes(s.code);
                  const notBuilt = !s.builder_available;
                  return (
                    <li
                      key={s.code}
                      className="flex items-start gap-3 text-sm"
                    >
                      {notBuilt ? (
                        // Amber "platform owes you this" indicator —
                        // distinct from grey 'not yet attempted' and
                        // green 'done'.
                        <Circle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                      ) : passed ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-700" />
                      ) : (
                        <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/40" />
                      )}
                      <div className="min-w-0 flex flex-wrap items-baseline gap-x-2">
                        <span className="font-mono font-medium">{s.code}</span>
                        <span className="text-muted-foreground">·</span>
                        <span className="font-medium">{s.description}</span>
                        {notBuilt && (
                          <span
                            className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-100"
                            title="IRIS assigned this scenario but the platform doesn't yet ship a payload-builder for it."
                          >
                            platform: not yet supported
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-3 border-t pt-3 text-xs text-muted-foreground">
                Once your sandbox token is saved, run the runnable
                scenarios from the{" "}
                <Link
                  to="/fbr/scenarios"
                  className="underline-offset-2 hover:underline"
                >
                  scenario tests page
                </Link>
                . When every runnable row turns green, the production
                token field below unlocks. Rows marked "platform: not
                yet supported" don't block activation — they're work
                the platform team owes us.
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* =========================================================
          SANDBOX
          ========================================================= */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Sandbox token</CardTitle>
          <CardDescription>
            Paste the bearer token PRAL issued for the sandbox
            environment. The same token authenticates every endpoint
            (post / validate / edit / cancel) — PRAL's model is one
            bearer per (taxpayer × environment).
            {status?.production?.has_token && status.production.is_active ? (
              <span className="ml-1 font-medium text-amber-700">
                Production is active — this sandbox token has been deactivated
                and is no longer used for submissions. Live invoices go to
                production only.
              </span>
            ) : status?.sandbox?.has_token ? (
              <span className="ml-1 font-medium text-green-700">
                Sandbox configured — paste a new token to rotate.
              </span>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSaveSandbox} className="space-y-3">
            <div>
              <Label htmlFor="sb-endpoint">API endpoint</Label>
              <Input
                id="sb-endpoint"
                value={sandboxEndpoint}
                onChange={(e) => setSandboxEndpoint(e.target.value)}
                placeholder={PRAL_DEFAULT_URL}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Default <code>{PRAL_DEFAULT_URL}</code>. <strong>Paste
                only the gateway host</strong> (no <code>/di_data/...</code>
                path). The client appends the correct path for each
                endpoint (post / validate / etc.) at call time. If you
                accidentally paste the full submission URL we strip the
                path automatically before saving.
              </p>
            </div>
            <div>
              <Label htmlFor="sb-token">Bearer token</Label>
              <Input
                id="sb-token"
                type="password"
                value={sandboxToken}
                onChange={(e) => setSandboxToken(e.target.value)}
                placeholder={
                  status?.sandbox?.token_preview
                    ? `Current: ${status.sandbox.token_preview} — paste a new token to rotate`
                    : "paste sandbox token here"
                }
                autoComplete="off"
              />
              {status?.sandbox?.token_preview && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Token on file:{" "}
                  <code className="font-mono">
                    {status.sandbox.token_preview}
                  </code>
                  . The full bearer is encrypted at rest and never
                  shown again — leave this field blank to keep it and
                  only update the endpoint, or paste a new token to
                  rotate.
                </p>
              )}
            </div>

            <TestConnectionStrip result={sandboxTest} loading={test.isPending} />
            <SavedStrip savedAt={sandboxSaved} environment="sandbox" />

            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onTestSandbox}
                disabled={!sandboxToken || !sandboxEndpoint || test.isPending}
                title={
                  !sandboxToken
                    ? "Paste a token to test the connection"
                    : "Probe PRAL with this token + endpoint"
                }
              >
                {test.isPending ? "Testing…" : "Test connection"}
              </Button>
              {/* Save is enabled when:
                 - we have an endpoint (always pre-filled) AND
                 - EITHER a new token is typed OR a token already exists
                   on file (endpoint-only update). */}
              <Button
                type="submit"
                disabled={
                  !sandboxEndpoint
                  || submitSandbox.isPending
                  || (!sandboxToken && !status?.sandbox?.has_token)
                }
              >
                {submitSandbox.isPending
                  ? "Saving…"
                  : status?.sandbox?.has_token && !sandboxToken
                    ? "Save (keep existing token)"
                    : "Save sandbox token"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* =========================================================
          PRODUCTION
          ========================================================= */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Production token</CardTitle>
          <CardDescription>
            Activate production once every eligible scenario passes in
            sandbox.{" "}
            <Link to="/fbr/scenarios" className="underline-offset-2 hover:underline">
              Run scenarios →
            </Link>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!status?.all_scenarios_passed && !isPlatformStaff ? (
            <p className="text-sm text-amber-700">
              Production activation is locked until every eligible
              scenario reports <strong>success</strong>. Status:{" "}
              {status?.passed_scenarios.length ?? 0} passed /{" "}
              {status?.eligible_scenarios.length ?? 0} eligible.
            </p>
          ) : status?.production?.has_token ? (
            <p className="text-sm text-green-700">
              Production is active. Submissions go to live FBR.
            </p>
          ) : (
            <form onSubmit={onActivateProd} className="space-y-3">
              <div>
                <Label htmlFor="pr-endpoint">API endpoint</Label>
                <Input
                  id="pr-endpoint"
                  value={prodEndpoint}
                  onChange={(e) => setProdEndpoint(e.target.value)}
                  placeholder={PRAL_DEFAULT_URL}
                />
              </div>
              <div>
                <Label htmlFor="pr-token">Bearer token</Label>
                <Input
                  id="pr-token"
                  type="password"
                  value={prodToken}
                  onChange={(e) => setProdToken(e.target.value)}
                  placeholder={
                    status?.production?.token_preview
                      ? `Current: ${status.production.token_preview} — paste a new token to rotate`
                      : "paste production token here"
                  }
                  autoComplete="off"
                />
                {status?.production?.token_preview && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Token on file:{" "}
                    <code className="font-mono">
                      {status.production.token_preview}
                    </code>
                    . Leave blank to keep it; paste a new bearer to rotate.
                  </p>
                )}
              </div>

              {/* Platform-staff escape hatch: activate a token FBR already
                  issued (sandbox cleared on the FBR portal / via the IMS)
                  without our scenario runner being green. Only shown to
                  platform staff and only relevant when scenarios aren't
                  marked passed in our system. The backend re-checks the
                  caller is platform staff. */}
              {isPlatformStaff && !status?.all_scenarios_passed && (
                <label className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={bypassScenarios}
                    onChange={(e) => setBypassScenarios(e.target.checked)}
                  />
                  <span>
                    <strong>FBR already issued this production token.</strong>{" "}
                    Activate without our sandbox scenario runner (the token's
                    existence means FBR already cleared sandbox testing on its
                    portal). Platform-staff only; recorded in the audit log.
                  </span>
                </label>
              )}

              <TestConnectionStrip result={prodTest} loading={test.isPending} />
              <SavedStrip savedAt={prodSaved} environment="production" />

              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onTestProd}
                  disabled={!prodToken || !prodEndpoint || test.isPending}
                >
                  {test.isPending ? "Testing…" : "Test connection"}
                </Button>
                <Button
                  type="submit"
                  disabled={
                    !prodEndpoint
                    || activateProd.isPending
                    || (!prodToken && !status?.production?.has_token)
                  }
                >
                  {activateProd.isPending
                    ? "Activating…"
                    : status?.production?.has_token && !prodToken
                      ? "Save (keep existing token)"
                      : "Activate production"}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      {/* =========================================================
          POS CONNECTIONS (per branch) — POS tenants only; a back-office
          Digital-Invoicing tenant has no POS terminals to connect.
          ========================================================= */}
      {!isDigitalOnly && <PosConnectionsCard />}

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100"
        >
          {error}
        </div>
      )}
    </div>
  );
}

/**
 * Per-branch FBR POS connection status.
 *
 * This is the "are my POS terminals talking to FBR?" view — it mirrors the
 * Connected/Disconnected state the FBR portal shows. A branch is Connected
 * once it has had at least one invoice validated by FBR; until then it's
 * Disconnected (even if a POS ID is registered). The actual binding to FBR is
 * the production token above — once a sale from a registered branch is
 * submitted with that token, the branch flips to Connected here and on the
 * FBR portal. POS ID + Code are edited per-branch on the Branches page.
 */
function PosConnectionsCard() {
  const { data, isLoading } = useFbrPosStatus();
  const branches = data?.branches ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <MonitorSmartphone className="h-4 w-4" /> POS connections
        </CardTitle>
        <CardDescription>
          FBR connection status for each outlet. A branch shows{" "}
          <strong>Connected</strong> once it has successfully transmitted at
          least one invoice using your token — the same state the FBR portal
          reports. Enter each outlet's FBR <strong>POS ID</strong> and{" "}
          <strong>Code</strong> on the{" "}
          <Link to="/branches" className="underline-offset-2 hover:underline">
            Branches page
          </Link>
          .
          {data && !data.token_present && (
            <span className="ml-1 font-medium text-amber-700">
              No active token yet — configure one above to start connecting.
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : branches.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No branches yet. Add an outlet on the{" "}
            <Link to="/branches" className="underline-offset-2 hover:underline">
              Branches page
            </Link>{" "}
            first.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {branches.map((b) => (
              <li
                key={b.branch_id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{b.branch_name}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {b.branch_code}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {b.fbr_pos_id ? (
                      <>
                        POS ID <span className="font-mono">{b.fbr_pos_id}</span>
                        {b.fbr_pos_code && (
                          <>
                            {" · "}Code{" "}
                            <span className="font-mono">{b.fbr_pos_code}</span>
                          </>
                        )}
                      </>
                    ) : (
                      <span className="text-amber-700">
                        No FBR POS ID set —{" "}
                        <Link
                          to="/branches"
                          className="underline-offset-2 hover:underline"
                        >
                          add it
                        </Link>
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {b.last_validated_at && (
                    <span className="text-xs text-muted-foreground">
                      last:{" "}
                      {new Date(b.last_validated_at).toLocaleDateString()}
                    </span>
                  )}
                  {b.connected ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-100">
                      <CheckCircle2 className="h-3 w-3" /> Connected
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                      <Circle className="h-3 w-3" /> Disconnected
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Inline confirmation strip shown right after a successful token
 *  save. The mutation also flips the card's "Sandbox configured"
 *  green sentence (via React Query refetch of /fbr/status/), but
 *  that's easy to miss — this strip is loud, anchored next to the
 *  Save button, and includes the wall-clock time so the operator
 *  is certain the click registered. */
function SavedStrip({
  savedAt,
  environment,
}: {
  savedAt: string | null;
  environment: "sandbox" | "production";
}) {
  if (!savedAt) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100"
    >
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <strong>
          {environment === "sandbox"
            ? "Sandbox token saved"
            : "Production activated"}
        </strong>{" "}
        at <span className="font-mono">{savedAt}</span>. The token is
        encrypted at rest and will be used by every PRAL call from
        now on.
      </div>
    </div>
  );
}


/** Inline status strip the Test Connection button paints below the
 *  form. Renders nothing until a test has been run. WCAG-safe colour
 *  contrast: dark text on a 50/950 tint, ~10:1 ratios. */
function TestConnectionStrip({
  result,
  loading,
}: {
  result: TestTokenResult | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-100">
        <Loader2 className="h-4 w-4 animate-spin" />
        Asking PRAL to validate the token…
      </div>
    );
  }
  if (!result) return null;
  if (result.ok) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100"
      >
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <strong>Connection OK.</strong> PRAL accepted the token and
          returned {result.uom_count} UoMs from{" "}
          <code className="text-xs">/pdi/v1/uom</code>. Click "Save"
          to persist it.
        </div>
      </div>
    );
  }
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100"
    >
      <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <strong>Connection failed.</strong> {result.detail}
      </div>
    </div>
  );
}
