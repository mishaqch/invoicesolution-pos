import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Loader2,
  Play,
  Save,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { useAuthStore } from "@/stores/auth";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useApplyScenarioTemplate,
  useFbrScenarios,
  useFbrScenarioTemplates,
  useFbrStatus,
  useRunScenarios,
  useRunSingleScenario,
  useSaveScenarioTemplate,
  type FbrScenarioRow,
} from "@/lib/queries";

// ---------------------------------------------------------------------------
// Status legend pill
// ---------------------------------------------------------------------------
//
// Builder-unavailable scenarios get an amber "Not yet supported" pill
// BEFORE checking row.status — even if a previous run left a stale
// FbrScenarioTest record, the current code is unbuildable so the
// operator needs to see that, not the stale status.

function ScenarioStatus({
  row,
  builderAvailable,
}: {
  row: FbrScenarioRow | undefined;
  builderAvailable: boolean;
}) {
  if (!builderAvailable) {
    return (
      <Badge
        variant="outline"
        className="border-amber-400 bg-amber-50 text-amber-900 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
        title="IRIS assigned this scenario but the platform can't run it yet."
      >
        Not yet supported
      </Badge>
    );
  }
  if (!row) return <Badge variant="outline">Pending</Badge>;
  if (row.status === "success") return <Badge variant="default">Success</Badge>;
  if (row.status === "failed")
    return <Badge variant="destructive">Failed</Badge>;
  if (row.status === "submitting")
    return <Badge variant="outline">Running…</Badge>;
  if (row.status === "not_implemented") {
    return (
      <Badge
        variant="outline"
        className="border-amber-400 bg-amber-50 text-amber-900 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
      >
        Not yet supported
      </Badge>
    );
  }
  return <Badge variant="outline">Pending</Badge>;
}

// ---------------------------------------------------------------------------
// Status legend strip — shown above the grid so operators learn the colours.
// ---------------------------------------------------------------------------

function StatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 p-3 text-xs">
      <span className="font-medium">Legend:</span>
      <span className="inline-flex items-center gap-1.5">
        <Badge variant="outline">Pending</Badge>
        <span className="text-muted-foreground">Not yet run</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Badge variant="default">Success</Badge>
        <span className="text-muted-foreground">PRAL accepted</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Badge variant="destructive">Failed</Badge>
        <span className="text-muted-foreground">PRAL rejected</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Badge
          variant="outline"
          className="border-amber-400 bg-amber-50 text-amber-900 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
        >
          Not yet supported
        </Badge>
        <span className="text-muted-foreground">
          Platform doesn't ship a builder for this code yet
        </span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-card Request / Response editor — Postman-style collapsible panel
// with inline JSON editing.
// ---------------------------------------------------------------------------
//
// Operator flow:
//   1) Click "Show request / response" — sees what we sent + what PRAL replied
//   2) Edits the request JSON in the textarea (e.g. tweak salesTaxApplicable)
//   3) Clicks "Send edited payload" — backend sends the edited JSON verbatim
//   4) Card refreshes with the new PRAL response
//
// The edit is one-off. The next plain "Run" / "Retry" button click uses the
// builder code again — the override is NOT persisted on the scenario row.

interface RequestResponseEditorProps {
  row: FbrScenarioRow;
  /** Sends the textarea contents (parsed JSON) to the per-scenario run endpoint. */
  onSendEdited: (payload: unknown) => Promise<void>;
  /** Whether the parent is currently dispatching a Send (controls Spinner). */
  isSending: boolean;
  /** Disable the editor entirely (e.g. no sandbox token configured). */
  disabled: boolean;
}

function RequestResponseEditor({
  row,
  onSendEdited,
  isSending,
  disabled,
}: RequestResponseEditorProps) {
  const [open, setOpen] = useState(false);

  // Textarea state. Seeded from the row's last_request_payload; the
  // operator's edits live in `editJson` until they hit Send. When a
  // new server-side payload arrives (after a successful run), we
  // reset the textarea to that payload via the useEffect below — so
  // the next edit starts from the latest state, not a stale draft.
  const initialJson = row.last_request_payload != null
    ? JSON.stringify(row.last_request_payload, null, 2)
    : "";
  const [editJson, setEditJson] = useState(initialJson);
  const [lastSeenInitial, setLastSeenInitial] = useState(initialJson);
  const [parseError, setParseError] = useState<string | null>(null);

  if (initialJson !== lastSeenInitial) {
    // Server payload changed (new PRAL response landed). Reset our
    // local state to the latest server value. Runs inline rather than
    // in an effect to avoid a flash of stale content.
    setLastSeenInitial(initialJson);
    setEditJson(initialJson);
    setParseError(null);
  }

  if (!row.last_request_payload && !row.last_response_payload) {
    return null;
  }

  async function handleSend() {
    try {
      const parsed = JSON.parse(editJson);
      setParseError(null);
      await onSendEdited(parsed);
    } catch (err) {
      setParseError(
        err instanceof Error ? err.message : "Invalid JSON.",
      );
    }
  }

  function handleReset() {
    setEditJson(initialJson);
    setParseError(null);
  }

  const edited = editJson !== initialJson;

  return (
    <div className="mt-2 border-t pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        {open ? "Hide" : "Show / edit"} request &amp; response
      </button>
      {open && (
        <div className="mt-2 space-y-3">
          {row.last_request_payload != null && (
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Request payload (editable — edits sent only on click)
                </span>
                {edited && (
                  <button
                    type="button"
                    onClick={handleReset}
                    className="text-[10px] text-muted-foreground hover:underline"
                  >
                    Reset to last payload
                  </button>
                )}
              </div>
              <textarea
                value={editJson}
                onChange={(e) => {
                  setEditJson(e.target.value);
                  if (parseError) setParseError(null);
                }}
                spellCheck={false}
                disabled={disabled || isSending}
                rows={Math.min(18, Math.max(8, editJson.split("\n").length))}
                className="w-full rounded border bg-muted/30 p-2 font-mono text-[11px] leading-snug focus:outline-none focus:ring-1 focus:ring-ring"
              />
              {parseError && (
                <div className="mt-1 rounded bg-red-50 p-2 text-[11px] text-red-900 dark:bg-red-950 dark:text-red-100">
                  <strong>JSON parse error:</strong> {parseError}
                </div>
              )}
              <div className="mt-2 flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleSend}
                  disabled={disabled || isSending || !edited}
                  className="text-xs"
                  title={
                    !edited
                      ? "Edit the JSON above first"
                      : "Send your edited payload to PRAL"
                  }
                >
                  {isSending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="mr-1 h-3.5 w-3.5" />
                  )}
                  Send edited payload
                </Button>
                <span className="text-[10px] text-muted-foreground">
                  One-off — does not affect future plain "Run" calls.
                </span>
              </div>
            </div>
          )}
          {row.last_response_payload != null && (
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                PRAL response
              </div>
              <pre className="max-h-72 overflow-auto rounded border bg-muted/40 p-2 text-[11px] leading-snug">
                {JSON.stringify(row.last_response_payload, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Client-side JSON download helper.
// ---------------------------------------------------------------------------
//
// Builds a Blob from the payload, attaches a temporary <a download> to
// the DOM, clicks it programmatically, and revokes the object URL.
// Same pattern shadcn/Material/most React tutorials use. No server
// roundtrip needed — the payload is already in the client memory via
// FbrScenarioRow.last_request_payload.

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}


// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ScenariosPage() {
  const { data: status } = useFbrStatus();
  const { data: scenarios } = useFbrScenarios();
  const runAll = useRunScenarios();
  const runOne = useRunSingleScenario();
  // Track which scenario the per-card Run button is currently working
  // on (only one at a time). Lets us spin only that card's Run button,
  // not all of them.
  const [runningCode, setRunningCode] = useState<string | null>(null);

  // Render every scenario IRIS assigned to this tenant, even ones our
  // platform can't run yet (builder_available=false). The operator
  // needs to see SN026/SN027/SN028 etc. in the grid with a "Not yet
  // supported" pill — disappearing them silently was the old bug.
  const assigned = status?.assigned_scenarios ?? [];
  const byCode = new Map(
    scenarios?.results.map((r) => [r.scenario_code, r]) ?? [],
  );

  // Super-admin gates the "Save as template" button — templates are
  // a platform-level library and only ops staff curate them. Regular
  // tenant operators can still APPLY templates (read-only consumer).
  const user = useAuthStore((s) => s.user);
  const isPlatformStaff = !!user?.is_platform_staff;

  // Template lifecycle hooks.
  const { data: templates } = useFbrScenarioTemplates();
  const saveTemplate = useSaveScenarioTemplate();
  const applyTemplate = useApplyScenarioTemplate();

  // Per-code: which template the operator picked (applied next click).
  const [pickedTemplate, setPickedTemplate] = useState<Record<string, string>>({});
  // Top-level page error for failed save / apply operations.
  const [pageError, setPageError] = useState<string | null>(null);

  async function handleRunOne(code: string) {
    setRunningCode(code);
    try {
      await runOne.mutateAsync({ code });
    } finally {
      setRunningCode(null);
    }
  }

  // Send an edited payload (from the inline JSON editor) for one
  // scenario. Same `runningCode` lock so only one card spins at a
  // time. The override is one-off — the server doesn't persist it.
  async function handleSendEdited(code: string, payload: unknown) {
    setRunningCode(code);
    try {
      await runOne.mutateAsync({ code, payload });
    } finally {
      setRunningCode(null);
    }
  }

  async function handleSaveAsTemplate(
    code: string, payload: unknown,
  ) {
    setPageError(null);
    const name = window.prompt(
      `Save the SN${code.slice(2)} payload as a template.\n\n` +
      "Name this template (recommended: 'Wholesaler/Retailer — " + code + "' " +
      "or whatever business type it fits). Future tenants of the same " +
      "type can apply it in one click.",
      "",
    );
    if (!name || !name.trim()) return;
    try {
      await saveTemplate.mutateAsync({
        code, name: name.trim(), payload,
      });
    } catch (e) {
      setPageError(extractApiErrorMessage(e));
    }
  }

  async function handleApplyTemplate(code: string) {
    setPageError(null);
    const templateId = pickedTemplate[code];
    if (!templateId) return;
    setRunningCode(code);
    try {
      await applyTemplate.mutateAsync({ code, templateId });
    } catch (e) {
      setPageError(extractApiErrorMessage(e));
    } finally {
      setRunningCode(null);
    }
  }

  const tokenMissing = !status?.sandbox?.has_token;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Sandbox scenarios
          </h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Each scenario submits a synthetic invoice to PRAL's sandbox
            (the exact saleType, rate, and SRO schedule each scenarioId
            requires) and reports PRAL's response. Run them one at a
            time to iterate on a failing scenario, or "Run all" to
            verify the whole list. All eligible scenarios must pass
            before the production token activates.
          </p>
        </div>
        <Button
          onClick={() => runAll.mutate()}
          disabled={runAll.isPending || tokenMissing}
        >
          {runAll.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Run all eligible
        </Button>
      </div>

      {tokenMissing && (
        <p className="text-sm text-amber-700">
          A sandbox token is required first. Paste yours under FBR → Setup.
        </p>
      )}

      <StatusLegend />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {assigned.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No scenarios assigned yet. Open the tenant in the Django
            admin and paste the scenario list from the tenant's IRIS
            profile (or leave empty for the platform's nature × sector
            default).
          </p>
        ) : (
          assigned.map((s) => {
            const row = byCode.get(s.code);
            const isRunning =
              runningCode === s.code ||
              row?.status === "submitting";
            const runDisabled =
              tokenMissing || !s.builder_available || isRunning;
            return (
              <Card key={s.code} className="flex flex-col">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-sm font-mono">
                      {s.code}
                    </CardTitle>
                    <ScenarioStatus
                      row={row}
                      builderAvailable={s.builder_available}
                    />
                  </div>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col space-y-2 text-sm">
                  <p className="text-muted-foreground">{s.description}</p>

                  {!s.builder_available && (
                    <div className="rounded bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                      IRIS assigned this scenario, but our platform
                      doesn't yet ship a payload-builder for it. The
                      runner skips this code without contacting PRAL.
                      Contact the platform team to add support.
                    </div>
                  )}

                  {row?.fbr_invoice_number && (
                    <div className="text-xs">
                      <span className="text-muted-foreground">FBR #</span>{" "}
                      <span className="font-mono">
                        {row.fbr_invoice_number}
                      </span>
                    </div>
                  )}

                  {s.builder_available && row?.error_message && (
                    <div className="rounded bg-red-50 p-2 text-xs text-red-900">
                      <XCircle className="mr-1 inline h-3 w-3" />
                      {row.error_message}
                    </div>
                  )}

                  {row?.last_attempt_at && (
                    <div className="text-xs text-muted-foreground">
                      Last attempt:{" "}
                      {new Date(row.last_attempt_at).toLocaleString()}
                    </div>
                  )}

                  {/* Inline JSON editor + response inspector.
                      Only renders when we actually have a previous
                      submission attached to this scenario_code. */}
                  {row &&
                    (row.last_request_payload != null ||
                      row.last_response_payload != null) && (
                      <RequestResponseEditor
                        row={row}
                        onSendEdited={(payload) =>
                          handleSendEdited(s.code, payload)
                        }
                        isSending={isRunning}
                        disabled={tokenMissing}
                      />
                    )}

                  {/* Action footer: Run (left, primary) + Download
                      (right, icon-only). Download is enabled whenever
                      we have a payload to write — even on cards that
                      have never run, the backend's `last_request_payload`
                      is null and Download is hidden. */}
                  <div className="mt-auto flex items-center gap-2 pt-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRunOne(s.code)}
                      disabled={runDisabled}
                      className="flex-1"
                    >
                      {isRunning ? (
                        <>
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          Running…
                        </>
                      ) : (
                        <>
                          <Play className="mr-1 h-3.5 w-3.5" />
                          {row?.status === "success"
                            ? "Re-run"
                            : row?.status === "failed"
                              ? "Retry"
                              : "Run"}
                        </>
                      )}
                    </Button>
                    {row?.last_request_payload != null && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          downloadJson(
                            `${s.code}.json`,
                            row.last_request_payload,
                          )
                        }
                        title="Download this scenario's request payload as JSON"
                        className="shrink-0"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    {/* Save-as-template button — super-admin only.
                        Visible after at least one run (we need a payload
                        to save). Captures the LAST request as a
                        reusable template. */}
                    {isPlatformStaff &&
                      row?.last_request_payload != null && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            handleSaveAsTemplate(
                              s.code, row.last_request_payload,
                            )
                          }
                          title="Save this payload as a reusable template (super-admin only)"
                          className="shrink-0"
                        >
                          <Save className="h-3.5 w-3.5" />
                        </Button>
                      )}
                  </div>

                  {/* Template picker — shown to ALL operators (consume
                      what super-admin curated). Renders only if there
                      are templates for this scenario_code. */}
                  {(() => {
                    const codeTemplates = (templates?.results ?? []).filter(
                      (t) => t.scenario_code === s.code,
                    );
                    if (codeTemplates.length === 0) return null;
                    return (
                      <div className="mt-2 border-t pt-2 space-y-1.5">
                        <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                          Apply saved template
                        </div>
                        <div className="flex items-center gap-2">
                          <Select
                            value={pickedTemplate[s.code] || ""}
                            onChange={(e) =>
                              setPickedTemplate((m) => ({
                                ...m,
                                [s.code]: e.target.value,
                              }))
                            }
                            className="flex-1 text-xs"
                          >
                            <option value="">— pick a template —</option>
                            {codeTemplates.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name}
                              </option>
                            ))}
                          </Select>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={
                              runDisabled ||
                              !pickedTemplate[s.code]
                            }
                            onClick={() => handleApplyTemplate(s.code)}
                            className="shrink-0 text-xs"
                          >
                            Apply
                          </Button>
                        </div>
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {pageError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {pageError}
        </div>
      )}

      {status?.all_scenarios_passed && (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
          <CheckCircle2 className="mr-1 inline h-4 w-4" />
          All scenarios passed. You can activate production from FBR → Setup.
        </div>
      )}
    </div>
  );
}
