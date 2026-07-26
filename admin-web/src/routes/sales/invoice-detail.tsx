import { ArrowLeft, CheckCircle2, Download, FilePlus2, FileText, Lock, Mail, MessageCircle, MoreHorizontal, Pencil, RefreshCw, Send, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
// See invoices.tsx for why this is a named import, not the default.
import { QRCode } from "react-qr-code";

import {
  invoiceStatusHint,
  invoiceStatusLabel,
  invoiceStatusVariant,
} from "@/features/invoices/status";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, extractApiErrorMessage } from "@/lib/api";
import { money, qty } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NumberInput } from "@/components/ui/number-input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useCancelInvoice,
  useCancelInvoiceItem,
  useDeleteDraftInvoice,
  useMarkCancelledOnFbr,
  useEditInvoiceItem,
  useFbrSubmissions,
  useInvoice,
  usePrecheckInvoice,
  useResubmitInvoice,
  useValidateInvoice,
  type PrecheckResult,
  type AdminInvoice,
  type FbrSubmissionRow,
  type ValidateInvoiceResult,
} from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";
import { useFbrConnectionType } from "@/features/modules/hooks";

async function openPdf(invoiceId: string, invoiceNumber: string, download: boolean) {
  const access = useAuthStore.getState().access;
  const url = `/api/sales/invoices/${invoiceId}/pdf/${download ? "?download=1" : ""}`;
  const resp = await fetch(url, {
    headers: { ...(access ? { Authorization: `Bearer ${access}` } : {}) },
  });
  if (!resp.ok) {
    window.alert(`Failed to fetch PDF: ${resp.status}`);
    return;
  }
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  if (download) {
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `invoice-${invoiceNumber}.pdf`;
    a.click();
  } else {
    window.open(blobUrl, "_blank");
  }
  // Don't revoke immediately — Safari needs the URL alive for the new tab.
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}


function timeUntilDeadline(deadline: string | null): { remaining: string; expired: boolean } | null {
  if (!deadline) return null;
  const ms = new Date(deadline).getTime() - Date.now();
  if (ms <= 0) return { remaining: "expired", expired: true };
  const hours = Math.floor(ms / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  return { remaining: `${hours}h ${minutes}m`, expired: false };
}

// Invoice statuses the server accepts as a reference for a debit note.
// Mirror of the gate in apps/sales/views.py manual_create.
const DEBIT_NOTE_REFERENCEABLE_STATUSES = new Set([
  "valid", "finalized", "edited", "partially_edited",
  "partially_cancelled", "partially_edited_and_cancelled",
]);

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  // Tax authority this tenant fiscalizes with. PRA POS tenants (pra_cloud)
  // must see "PRA" on the buttons/messages; everyone else sees "FBR".
  const authority = useFbrConnectionType() === "pra_cloud" ? "PRA" : "FBR";
  const { data: invoice, isLoading } = useInvoice(id);
  const cancel = useCancelInvoice();
  const cancelItem = useCancelInvoiceItem();
  const markCancelledOnFbr = useMarkCancelledOnFbr();
  const editItem = useEditInvoiceItem();
  const resubmit = useResubmitInvoice();
  const validate = useValidateInvoice();
  const precheck = usePrecheckInvoice();
  const [precheckResult, setPrecheckResult] = useState<PrecheckResult | null>(null);
  const qc = useQueryClient();

  // After a POS cloud fiscalization, the fiscal number arrives ASYNC (a worker
  // posts to the authority cloud). Poll the invoice a few times so the QR +
  // downloadable PDF appear on THIS page automatically, without a manual
  // refresh. Stops as soon as fbr_invoice_number lands (or after ~20s).
  async function pollForFbrNumber(invoiceId: string) {
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      await qc.invalidateQueries({ queryKey: ["invoice", invoiceId] });
      const fresh = qc.getQueryData<AdminInvoice>(["invoice", invoiceId]);
      if (fresh?.fbr_invoice_number) {
        setFiscalMsg({ ok: true, done: true, text: `Fiscalized! ${authority} Invoice #${fresh.fbr_invoice_number} — QR + PDF are ready below.` });
        return;
      }
    }
  }
  const deleteDraft = useDeleteDraftInvoice();
  const [validateResult, setValidateResult] = useState<ValidateInvoiceResult | null>(null);
  const [fiscalizing, setFiscalizing] = useState(false);
  // `done` marks a FINAL success (fiscal number issued) — those auto-dismiss;
  // errors and the "waiting…" progress message stay until replaced.
  const [fiscalMsg, setFiscalMsg] = useState<{ ok: boolean; text: string; done?: boolean } | null>(null);
  const [fiscalMsgFading, setFiscalMsgFading] = useState(false);

  // Auto-dismiss a final fiscalization-success banner: hold ~5s, fade out over
  // ~0.6s, then remove. Only for `done` success — never for errors or the
  // in-progress "waiting…" message.
  useEffect(() => {
    if (!fiscalMsg?.ok || !fiscalMsg.done) return;
    setFiscalMsgFading(false);
    const fade = setTimeout(() => setFiscalMsgFading(true), 5000);
    const clear = setTimeout(() => { setFiscalMsg(null); setFiscalMsgFading(false); }, 5600);
    return () => { clearTimeout(fade); clearTimeout(clear); };
  }, [fiscalMsg]);
  const [showConfirm, setShowConfirm] = useState(false);
  const [reason, setReason] = useState("");
  const [itemPrompt, setItemPrompt] = useState<{ id: string; reason: string } | null>(null);
  const [editPrompt, setEditPrompt] = useState<{
    id: string;
    quantity: string;
    unit_price: string;
    tax_rate: string;
    reason: string;
    error?: string;
  } | null>(null);

  if (isLoading || !invoice) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  const deadline = timeUntilDeadline(invoice.edit_deadline_at);

  // Mirror the server-side rule in apps/fbr/rules.py.
  //
  // PRAL DI manual v1.6 §"Conditions for Invoice Cancellation":
  //   "Only e-invoices received through DI Integration are eligible
  //    for correction."
  //
  // → An invoice can only be edited or cancelled AFTER FBR has
  //   accepted it (status in valid / partially_* AND fbr_invoice_number
  //   is set). pending_sync, submitted and failed invoices have no
  //   FBR document to amend; the only operator action there is
  //   Resubmit. The server enforces this too, but we mirror it here
  //   so the buttons disappear instead of erroring on click.
  const FBR_ACCEPTED_STATES = new Set([
    "valid",
    "partially_edited",
    "partially_cancelled",
    "partially_edited_and_cancelled",
  ]);
  const isFbrAccepted =
    FBR_ACCEPTED_STATES.has(invoice.status)
    && !!invoice.fbr_invoice_number;

  // An UNSUBMITTED draft — never reached FBR (no number, pre-validation
  // status). These can be deleted + re-validated freely; a submitted/
  // fiscalized invoice can NEVER be edited or deleted (FBR immutability).
  const isDraft =
    !invoice.fbr_invoice_number
    && (invoice.status === "pending_sync" || invoice.status === "failed");

  // POS registration: the invoice's branch has an FBR POS ID. These fiscalize
  // via the tax authority's CLOUD IMS from our server (FBR gw.fbr.gov.pk/imsp
  // or PRA ims.pral.com.pk) using the branch POS token — NOT the direct DI-API
  // tenant-token flow. So show the one-click "Fiscalize with FBR" (cloud)
  // button and hide the DI-API Validate/Submit buttons.
  const isPosFiscalizationTenant = !!invoice.branch_fbr_pos_id;

  const canCancel =
    isFbrAccepted
    && invoice.status !== "cancelled"
    && invoice.status !== "finalized"
    && !(deadline?.expired ?? false);

  // An invoice can be cancelled on the FBR portal directly (outside our
  // platform). PRAL has no status-query endpoint, so we can't detect it — this
  // lets an owner/manager record it once it's happened. Offer it for any
  // FBR-validated invoice (including finalized/past-72h) that isn't already
  // cancelled here.
  const canMarkCancelledOnFbr =
    !!invoice.fbr_invoice_number
    && invoice.status !== "cancelled"
    && ["valid", "finalized", "partially_cancelled",
        "partially_edited", "partially_edited_and_cancelled"].includes(invoice.status);

  // Surface the same friendly reasons rules.py emits, so a hover on
  // the disabled cancel-chip explains the state in plain English.
  const lockedReason = canCancel ? null : (
    invoice.status === "pending_sync"
      ? "Awaiting FBR submission — edits unlock once FBR accepts the invoice."
      : invoice.status === "submitted"
        ? "Awaiting FBR validation — edits unlock once FBR returns a number."
        : invoice.status === "failed"
          ? "Invoice was rejected by FBR. Resubmit first, then edit within 72 h."
          : invoice.status === "cancelled"
            ? "Already cancelled"
            : invoice.status === "finalized"
              ? "Already finalized to a return"
              : deadline?.expired
                ? "72-hour cancel window has passed (use a credit note instead)"
                : "Not eligible for cancellation"
  );

  return (
    <div className="space-y-4">
      {/* Top utility row: back-link on the left, lock chip on the right
          when the invoice isn't editable. The chip's variant matches
          the underlying invoice status (amber for pending_sync /
          submitted, red for failed, muted for cancelled/finalized,
          etc.) so the lock-state is recognizable at a glance without
          reading the tooltip. */}
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/sales"
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1 h-4 w-4" /> Back to sales
        </Link>
        {!canCancel && lockedReason && (
          <Badge
            variant={invoiceStatusVariant(invoice.status)}
            title={lockedReason}
            className="max-w-[60ch] truncate"
          >
            <Lock className="mr-1 h-3 w-3 shrink-0" aria-hidden />
            {invoiceStatusLabel(invoice.status)} — cannot amend
          </Badge>
        )}
      </div>

      {/* ============================================================
          Title row — local invoice no + a single sub-line of meta.
          Kept deliberately spare so even on a narrow viewport the
          page header doesn't wrap into a wall of chrome. The full
          FBR number lives in the FBR-validated card on the right.
          ============================================================ */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">
            {invoice.local_invoice_number}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <Badge
              variant={invoiceStatusVariant(invoice.status)}
              title={invoiceStatusHint(invoice.status)}
            >
              {invoiceStatusLabel(invoice.status)}
            </Badge>
            <span className="tabular-nums">{invoice.invoice_date}</span>
            {deadline && !deadline.expired && (
              <Badge
                variant="outline"
                className="text-amber-700 border-amber-300"
                title="Within this window you can edit individual line items or cancel the invoice. After it closes, you must use a credit note instead."
              >
                {deadline.remaining} left to amend
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================
          Action bar — wraps to a second row on narrow viewports. Five
          visible buttons max, with the rarely-used Download + Add
          debit note folded into a "More" overflow so the toolbar
          stays readable.

          Order is deliberate:
            1. Validate with FBR  (primary FBR action; always available)
            2. Submit to FBR      (only shown when not yet submitted)
            3. View PDF           (frequent)
            4. Send to buyer      (frequent, has its own popover)
            5. More ▾             (overflow: Download PDF, Add debit note)
            6. Cancel sale        (destructive; pushed to far right)
          ============================================================ */}
      <div className="flex flex-wrap items-center gap-2">
        {/* DI-API "Validate with FBR" — only for DI-API tenants. Hidden for
            SDC/POS tenants (they use the SDC button below; the DI-API path
            would error with "no token"). */}
        {!isPosFiscalizationTenant && (
        <Button
          variant="outline"
          onClick={async () => {
            setValidateResult(null);
            try {
              const r = await validate.mutateAsync(invoice.id);
              setValidateResult(r);
            } catch (e) {
              // 502 from our /validate/ endpoint means PRAL's gateway
              // misbehaved (timeout / non-JSON page / 5xx). The
              // backend returns a JSON body with `kind: "transient"`
              // + a human-readable `detail`. Pull those through so
              // the UI shows the right amber "service flaky" strip
              // instead of the misleading red "rejected" strip.
              if (e instanceof ApiError && e.data && typeof e.data === "object") {
                const d = e.data as {
                  kind?: "transient"; detail?: string; error?: string;
                };
                setValidateResult({
                  valid: false,
                  kind: d.kind,
                  error: d.detail ?? d.error ?? `Validate failed (HTTP ${e.status}).`,
                });
              } else {
                setValidateResult({
                  valid: false,
                  error: String((e as Error)?.message ?? "Validate failed"),
                });
              }
            }
          }}
          loading={validate.isPending}
          title={`Dry-run validate this invoice against ${authority}'s PRAL — no submission, just a lint check`}
        >
          <CheckCircle2
            className={`mr-1 h-4 w-4 ${validate.isPending ? "animate-pulse" : ""}`}
          />
          {validate.isPending ? "Validating…" : `Validate with ${authority}`}
        </Button>
        )}

        {/* Check invoice (LOCAL pre-submit): the IMS cloud has no dry-run, so
            this runs every check WE can (POS ID, fields, tax/UoM/HS math, buyer
            id) WITHOUT calling FBR — catches common rejects before committing.
            POS registrations only, until an FBR number exists. */}
        {isPosFiscalizationTenant && !invoice.fbr_invoice_number && invoice.status !== "cancelled" && (
          <Button
            variant="outline"
            disabled={precheck.isPending}
            onClick={async () => {
              setPrecheckResult(null);
              try {
                setPrecheckResult(await precheck.mutateAsync(invoice.id));
              } catch (e) {
                setFiscalMsg({ ok: false, text: extractApiErrorMessage(e) });
              }
            }}
            title="Run a local validity check (fields, POS ID, tax math) before fiscalizing. Does not call FBR."
          >
            <ShieldCheck className={`mr-1 h-4 w-4 ${precheck.isPending ? "animate-pulse" : ""}`} />
            {precheck.isPending ? "Checking…" : "Check invoice"}
          </Button>
        )}

        {/* Fiscalize a POS registration via the CLOUD (server-side). We no
            longer use a local SDC on the shop machine — the server posts the
            invoice to the tax authority's cloud IMS (FBR gw.fbr.gov.pk/imsp or
            PRA ims.pral.com.pk) with the branch's POS token and stores the
            fiscal number + QR. Shown until the invoice has an FBR number. */}
        {isPosFiscalizationTenant && !invoice.fbr_invoice_number && invoice.status !== "cancelled" && (
          <Button
            variant="default"
            disabled={fiscalizing}
            onClick={async () => {
              setFiscalizing(true);
              setFiscalMsg(null);
              setPrecheckResult(null);
              try {
                const updated = await resubmit.mutateAsync(invoice.id);
                if (updated.fbr_invoice_number) {
                  setFiscalMsg({ ok: true, done: true, text: `Fiscalized! ${authority} Invoice #${updated.fbr_invoice_number} — QR + PDF are ready below.` });
                } else {
                  // Queued/submitting — the fiscal number lands async via the
                  // cloud. Poll the invoice so the QR + PDF appear here without
                  // a manual refresh.
                  setFiscalMsg({ ok: true, text: `Sent to ${authority} — waiting for the fiscal number…` });
                  void pollForFbrNumber(invoice.id);
                }
              } catch (e) {
                setFiscalMsg({ ok: false, text: extractApiErrorMessage(e) });
              } finally {
                setFiscalizing(false);
              }
            }}
            title="Submit this invoice to the tax authority's cloud fiscalization (from our server) to get a fiscal invoice number + QR"
          >
            <CheckCircle2
              className={`mr-1 h-4 w-4 ${fiscalizing ? "animate-pulse" : ""}`}
            />
            {fiscalizing ? "Fiscalizing…" : `Fiscalize with ${authority}`}
          </Button>
        )}

        {/* Submit button: visible while the invoice hasn't yet been
            accepted by PRAL. The manual-invoice flow creates an invoice
            in `pending_sync` (treat as "draft" — saved locally but not
            yet sent to FBR). The operator clicks Submit when ready;
            PRAL then issues the FBR Invoice Number on success. Failed
            submissions can be retried via the same button. */}
        {!isPosFiscalizationTenant
          && (invoice.status === "failed" || invoice.status === "pending_sync")
          && !invoice.fbr_invoice_number && (
          <Button
            variant="default"
            onClick={() => void resubmit.mutateAsync(invoice.id)}
            loading={resubmit.isPending}
            title={
              invoice.status === "failed"
                ? "PRAL rejected this invoice. Fix the issue and click to retry."
                : "Send this invoice to PRAL to get an FBR Invoice Number"
            }
          >
            <RefreshCw
              className={`mr-1 h-4 w-4 ${resubmit.isPending ? "animate-spin" : ""}`}
            />
            {resubmit.isPending
              ? "Submitting…"
              : invoice.status === "failed"
                ? "Retry submission"
                : `Submit to ${authority}`}
          </Button>
        )}

        <Button
          variant="outline"
          onClick={() => openPdf(invoice.id, invoice.local_invoice_number, false)}
          title="Open the invoice PDF in a new tab"
        >
          <FileText className="mr-1 h-4 w-4" /> View PDF
        </Button>

        <SendToBuyer invoice={invoice} />

        <MoreActionsMenu
          items={[
            {
              label: "Download PDF",
              icon: <Download className="h-4 w-4" />,
              onSelect: () =>
                openPdf(invoice.id, invoice.local_invoice_number, true),
            },
            ...(DEBIT_NOTE_REFERENCEABLE_STATUSES.has(invoice.status)
              ? [{
                  label: "Add debit note",
                  icon: <FilePlus2 className="h-4 w-4" />,
                  onSelect: () =>
                    navigate("/sales/new", {
                      state: {
                        debitNote: {
                          invoiceType: "debit_note",
                          referenceInvoiceId: invoice.id,
                          referenceInvoiceNumber: invoice.local_invoice_number,
                          buyerName: invoice.buyer_name,
                          buyerNtnCnic: invoice.buyer_ntn_cnic,
                        },
                      },
                    }),
                }]
              : []),
          ]}
        />

        {/* Spacer + destructive action at the far right so it's never
            adjacent to a positive action by accident. */}
        <div className="grow" />
        {/* Draft (never sent to FBR) → can be deleted outright. A submitted/
            fiscalized invoice is never deletable (use Cancel sale instead). */}
        {isDraft && (
          <Button
            variant="destructive"
            loading={deleteDraft.isPending}
            onClick={async () => {
              if (!id) return;
              // A `failed` invoice was rejected by FBR but still holds its
              // stock deduction. Discarding it here is the way to put that
              // stock back — spell that out so the operator isn't left
              // wondering where the rejected sale's quantity went.
              const msg = invoice.status === "failed"
                ? "Discard this rejected invoice? FBR did not accept it. The stock it reserved will be added back to your on-hand."
                : "Delete this draft invoice? It hasn't been sent to FBR. Stock will be restored.";
              if (!window.confirm(msg)) return;
              try {
                await deleteDraft.mutateAsync(id);
                navigate("/sales", { replace: true });
              } catch (e) {
                window.alert(e instanceof Error ? e.message : "Could not delete the draft.");
              }
            }}
          >
            {invoice.status === "failed" ? "Discard & restore stock" : "Delete draft"}
          </Button>
        )}
        {canCancel && (
          <Button variant="destructive" onClick={() => setShowConfirm(true)}>
            Cancel sale
          </Button>
        )}
        {canMarkCancelledOnFbr && (
          <Button
            variant="outline"
            loading={markCancelledOnFbr.isPending}
            title="Use this only if you already cancelled this invoice on the FBR portal. It records the cancellation here — it does NOT cancel on FBR."
            onClick={() => {
              if (
                !window.confirm(
                  "Mark this invoice as cancelled on FBR?\n\nUse this ONLY if you have already cancelled it on the FBR portal. " +
                  "It updates the status here to match FBR — it does not send a cancellation to FBR.",
                )
              ) return;
              markCancelledOnFbr.mutate(invoice.id);
            }}
          >
            Mark cancelled on FBR
          </Button>
        )}
      </div>

      {fiscalMsg && (
        <div
          role="status"
          className={
            "flex items-start gap-2 rounded-md border px-3 py-2 text-sm transition-all duration-500 ease-out "
            + (fiscalMsg.ok
              ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100"
              : "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100")
            + (fiscalMsgFading ? " -translate-y-1 opacity-0" : " opacity-100")
          }
        >
          {fiscalMsg.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <X className="mt-0.5 h-4 w-4 shrink-0" />}
          <div>{fiscalMsg.text}</div>
        </div>
      )}

      {/* Local pre-submit check results (POS invoices). */}
      {precheckResult && (
        <div
          role="status"
          className={
            precheckResult.blocking
              ? "rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm dark:border-red-700 dark:bg-red-950"
              : precheckResult.issues.some((i) => i.severity === "warning")
                ? "rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-700 dark:bg-amber-950"
                : "rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm dark:border-emerald-700 dark:bg-emerald-950"
          }
        >
          <div className="mb-1 font-medium">
            {precheckResult.blocking
              ? "Fix these before fiscalizing:"
              : precheckResult.issues.length === 0
                ? `Looks good — no issues found. (Note: only ${authority} can confirm final acceptance.)`
                : "No blockers — a couple of things to double-check:"}
          </div>
          {precheckResult.issues.length > 0 && (
            <ul className="space-y-0.5">
              {precheckResult.issues.map((iss, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-0.5">
                    {iss.severity === "error" ? "❌" : iss.severity === "warning" ? "⚠️" : "ℹ️"}
                  </span>
                  <span>
                    <span className="font-mono text-xs text-muted-foreground">{iss.field}</span>{" "}
                    {iss.message}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-1.5 text-xs text-muted-foreground">
            This is a local check — it does not contact {authority}. {authority} POS
            has no dry-run; the authority confirms only on the real submission.
          </div>
        </div>
      )}

      {resubmit.isError && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100"
        >
          <strong>Submit failed.</strong>{" "}
          {String((resubmit.error as Error)?.message ?? "Unknown error")}
        </div>
      )}
      {/* Resubmit succeeds asynchronously — the API enqueues a Celery
          task and returns 200 immediately. Tell the operator what
          just happened so they don't think the click did nothing.
          Auto-refetches the invoice (the mutation's onSuccess does
          this); the status badge in the title row updates as soon
          as the worker processes the task. */}
      {resubmit.isSuccess && !invoice.fbr_invoice_number && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-start gap-2 rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-100"
        >
          <RefreshCw className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
          <div>
            <strong>Queued for submission to FBR.</strong> A worker is
            picking it up — refresh in a few seconds to see the FBR
            invoice number, or watch the submissions log below for the
            new roundtrip.
          </div>
        </div>
      )}

      {/* Validate-result strip — only visible right after the operator
          clicks Validate. Green if PRAL accepted the payload shape,
          red with PRAL's exact error message otherwise. The same
          roundtrip also lands in the FBR submissions log below.

          Color contrast: the `*-foreground` tokens are designed to
          sit on a SOLID `bg-*` background; on a 10%-opacity tint
          they wash out below WCAG 2.2 AA. We use darker, fixed
          colors (`text-emerald-800` / `text-red-800`) which give
          ~7.1:1 contrast against the 10%-tinted card — well above
          the 4.5:1 minimum for normal text. */}
      {validateResult && (
        <div
          role="status"
          aria-live="polite"
          className={
            "rounded-md border px-3 py-2 text-sm " +
            (validateResult.valid
              ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100"
              : validateResult.kind === "transient"
                ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
                : "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100")
          }
        >
          {validateResult.valid ? (
            <>
              <strong>✓ FBR PRAL says: Valid.</strong>{" "}
              Payload passes all of FBR's validation rules. Safe to
              submit when you're ready.
            </>
          ) : validateResult.kind === "transient" ? (
            <>
              <strong>⚠ FBR PRAL service is unreachable.</strong>{" "}
              {validateResult.error}
            </>
          ) : (
            <>
              <strong>✗ FBR PRAL rejected the payload.</strong>{" "}
              {validateResult.error_code && (
                <span className="font-mono">[{validateResult.error_code}]</span>
              )}{" "}
              {validateResult.error}
            </>
          )}
        </div>
      )}

      <div
        className={
          invoice.fbr_qr_payload
            ? "grid gap-4 md:grid-cols-4"
            : "grid gap-4 md:grid-cols-3"
        }
      >
        <Card>
          <CardHeader><CardTitle className="text-sm">Buyer</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {invoice.buyer_name ? (
              <>
                <div>{invoice.buyer_name}</div>
                {invoice.buyer_phone && <div className="text-muted-foreground">{invoice.buyer_phone}</div>}
              </>
            ) : (
              <span className="text-muted-foreground">Walk-in</span>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Totals</CardTitle></CardHeader>
          <CardContent className="text-sm">
            <Row k="Subtotal" v={`Rs ${money(invoice.subtotal)}`} />
            <Row k="Discount" v={`- Rs ${money(invoice.discount_total)}`} muted />
            <Row k="Tax" v={`Rs ${money(invoice.tax_total)}`} />
            <Row k="Grand total" v={`Rs ${money(invoice.grand_total)}`} bold />
            <Row k="Paid" v={`Rs ${money(invoice.paid_total)}`} />
            <Row k="Change" v={`Rs ${money(invoice.change_given)}`} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Payments</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {invoice.payments.length === 0 ? (
              <span className="text-muted-foreground">None</span>
            ) : (
              <ul className="space-y-1">
                {invoice.payments.map((p) => (
                  <li key={p.id} className="flex justify-between font-mono">
                    <span className="capitalize">{p.payment_method.replace("_", " ")}</span>
                    <span>Rs {money(p.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        {invoice.fbr_invoice_number && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-1.5">
                <span className="inline-flex h-2 w-2 rounded-full bg-success" aria-hidden />
                FBR-validated
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-2">
              {/* QR encodes EXACTLY the FBR fiscal invoice number string —
                  that's what the FBR Tax Asaan app verifies (scanning the QR
                  == entering the number). Encoding a JSON blob makes Tax Asaan
                  report "invalid". Mirrors the PDF + thermal receipt. */}
              <div className="rounded-md bg-white p-2">
                <QRCode
                  value={invoice.fbr_invoice_number}
                  size={120}
                  level="M"
                  aria-label="FBR-validated invoice QR code"
                />
              </div>
              {invoice.fbr_invoice_number && (
                <>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1">
                    {authority} Invoice #
                  </div>
                  {/* PRAL formats the number as 13-char seller NTN +
                      14-char unique tail. Visually separate them so
                      the reader can see which part identifies their
                      seller (NTN, same on every invoice) and which
                      part identifies THIS invoice (the tail). */}
                  <div className="font-mono text-[11px] tracking-tight text-center leading-tight">
                    {invoice.fbr_invoice_number.length === 27 ? (
                      <>
                        <span className="text-muted-foreground">
                          {invoice.fbr_invoice_number.slice(0, 13)}
                        </span>
                        <span className="font-bold">
                          {invoice.fbr_invoice_number.slice(13)}
                        </span>
                      </>
                    ) : (
                      <span>{invoice.fbr_invoice_number}</span>
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground text-center px-2 leading-snug mt-1">
                    Seller NTN (grey) + unique invoice ID (bold).<br />
                    Verify at{" "}
                    <a
                      href="https://e.fbr.gov.pk/"
                      target="_blank"
                      rel="noreferrer noopener"
                      className="underline"
                    >
                      e.fbr.gov.pk
                    </a>{" "}
                    or scan with FBR Tax Asaan.
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Line items</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="hidden sm:table-cell">#</TableHead>
                <TableHead>Product</TableHead>
                <TableHead className="hidden lg:table-cell">SKU</TableHead>
                <TableHead className="hidden xl:table-cell" title="PRAL HS code submitted to FBR for this line">
                  HS code
                </TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="hidden text-right md:table-cell">Unit price</TableHead>
                <TableHead className="hidden text-right md:table-cell">Tax</TableHead>
                <TableHead className="text-right">Line total</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoice.items.map((it) => {
                // Edit and cancel share the same upstream "within window"
                // gate (canCancel). Edit is also blocked when the line has
                // already been edited or cancelled. Cancel is also blocked
                // when the line is already edited.
                const lineGated = it.is_cancelled || it.is_edited || !canCancel;
                return (
                  <TableRow key={it.id} className={it.is_cancelled ? "opacity-50" : ""}>
                    <TableCell className="hidden sm:table-cell">{it.line_number}</TableCell>
                    <TableCell>
                      {it.is_cancelled && <span className="mr-1 text-xs font-bold text-destructive">C</span>}
                      {it.is_edited && <span className="mr-1 text-xs font-bold text-amber-600">E</span>}
                      <span className={it.is_cancelled ? "line-through" : ""}>
                        {it.product_name}
                      </span>
                      {/* SKU surfaced inline where the SKU column is hidden. */}
                      <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">
                        {it.product_sku}
                      </span>
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs lg:table-cell">{it.product_sku}</TableCell>
                    <TableCell className="hidden font-mono text-xs xl:table-cell">
                      {it.hs_code || (
                        <span className="text-muted-foreground italic">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">{qty(it.quantity)}</TableCell>
                    <TableCell className="hidden text-right font-mono md:table-cell">Rs {money(it.unit_price)}</TableCell>
                    <TableCell className="hidden text-right font-mono md:table-cell">Rs {money(it.tax_amount)}</TableCell>
                    <TableCell className="text-right font-mono">Rs {money(it.line_total)}</TableCell>
                    <TableCell className="text-right">
                      {!lineGated && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => setEditPrompt({
                              id: it.id,
                              quantity: it.quantity,
                              unit_price: it.unit_price,
                              tax_rate: it.tax_rate,
                              reason: "",
                            })}
                            className="rounded-md p-1 text-muted-foreground hover:bg-primary hover:text-primary-foreground"
                            aria-label="Edit this line"
                            title="Edit qty / price / tax (within 72h)"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setItemPrompt({ id: it.id, reason: "" })}
                            className="rounded-md p-1 text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
                            aria-label="Cancel this line"
                            title="Cancel this line"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <FbrSubmissionsPanel invoiceId={invoice.id} />

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Cancel sale</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This reverses the stock movements and marks the invoice
              cancelled. The 72-hour edit window and 10% monthly cap are
              enforced server-side; if they fail you'll see an error.
            </p>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason"
              className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowConfirm(false)}>Back</Button>
              <Button
                variant="destructive"
                disabled={cancel.isPending || reason.trim().length < 2}
                onClick={async () => {
                  await cancel.mutateAsync({ id: invoice.id, reason });
                  setShowConfirm(false);
                }}
              >
                {cancel.isPending ? "Cancelling…" : "Cancel sale"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {editPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Edit line item</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Patch the quantity, unit price, or tax rate. Totals
              recompute automatically. The change is sent to PRAL via
              <span className="mx-1 font-mono text-xs">editinvoice</span>
              and counts against this month's 10% amendment cap.
            </p>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="edit-qty">Quantity</Label>
                <NumberInput
                  id="edit-qty"
                  mode="decimal"
                  value={editPrompt.quantity}
                  onChange={(v) => setEditPrompt({ ...editPrompt, quantity: v })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-price">Unit price (Rs)</Label>
                <NumberInput
                  id="edit-price"
                  mode="decimal"
                  value={editPrompt.unit_price}
                  onChange={(v) => setEditPrompt({ ...editPrompt, unit_price: v })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-tax">Tax rate (%)</Label>
                <NumberInput
                  id="edit-tax"
                  mode="decimal"
                  value={editPrompt.tax_rate}
                  onChange={(v) => setEditPrompt({ ...editPrompt, tax_rate: v })}
                />
              </div>
            </div>

            <div className="mt-3 space-y-1.5">
              <Label htmlFor="edit-reason">Reason</Label>
              <textarea
                id="edit-reason"
                rows={2}
                value={editPrompt.reason}
                onChange={(e) => setEditPrompt({ ...editPrompt, reason: e.target.value })}
                placeholder="Why is this being amended? (audit log + sent to PRAL)"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
            </div>

            {editPrompt.error && (
              <p className="mt-2 text-sm text-destructive">{editPrompt.error}</p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditPrompt(null)}>
                Cancel
              </Button>
              <Button
                disabled={editItem.isPending || editPrompt.reason.trim().length < 2}
                onClick={async () => {
                  // Find the original line to figure out which fields changed.
                  const original = invoice.items.find((x) => x.id === editPrompt.id);
                  if (!original) return;
                  const patch: { quantity?: string; unit_price?: string; tax_rate?: string } = {};
                  if (editPrompt.quantity !== original.quantity) patch.quantity = editPrompt.quantity;
                  if (editPrompt.unit_price !== original.unit_price) patch.unit_price = editPrompt.unit_price;
                  if (editPrompt.tax_rate !== original.tax_rate) patch.tax_rate = editPrompt.tax_rate;
                  if (Object.keys(patch).length === 0) {
                    setEditPrompt({ ...editPrompt, error: "Nothing changed." });
                    return;
                  }
                  try {
                    await editItem.mutateAsync({
                      invoice_id: invoice.id,
                      item_id: editPrompt.id,
                      reason: editPrompt.reason,
                      ...patch,
                    });
                    setEditPrompt(null);
                  } catch (err) {
                    setEditPrompt({
                      ...editPrompt,
                      error: (err as Error).message ?? "Edit failed",
                    });
                  }
                }}
              >
                <Pencil className="mr-1 h-4 w-4" />
                {editItem.isPending ? "Saving…" : "Save edit"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {itemPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Cancel this line</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The line is removed from the invoice total and stock for it
              is returned. Other lines stay valid; the invoice flips to
              partially cancelled.
            </p>
            <textarea
              rows={3}
              value={itemPrompt.reason}
              onChange={(e) =>
                setItemPrompt({ ...itemPrompt, reason: e.target.value })
              }
              placeholder="Reason"
              className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setItemPrompt(null)}>Back</Button>
              <Button
                variant="destructive"
                disabled={cancelItem.isPending || itemPrompt.reason.trim().length < 2}
                onClick={async () => {
                  await cancelItem.mutateAsync({
                    invoice_id: invoice.id,
                    item_id: itemPrompt.id,
                    reason: itemPrompt.reason,
                  });
                  setItemPrompt(null);
                }}
              >
                {cancelItem.isPending ? "Cancelling…" : "Cancel line"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v, muted, bold }: { k: string; v: string; muted?: boolean; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${muted ? "text-muted-foreground" : ""} ${bold ? "font-semibold" : ""}`}>
      <span>{k}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}

// statusVariant moved to features/invoices/status.ts as
// invoiceStatusVariant — single source of truth across all invoice
// surfaces.


/**
 * Send-to-buyer popover.
 *
 * Two channels:
 *   - WhatsApp (https://wa.me/<phone>?text=…)
 *   - Email    (mailto:<email>?subject=…&body=…)
 *
 * Buyer phone / email are read off the linked Customer row when one
 * exists, else from buyer_phone on the invoice itself. Both fields
 * can be edited in the message body if the buyer is walk-in (no
 * stored contact). The message body includes:
 *   - Tenant business name
 *   - Local invoice number
 *   - FBR invoice number (if validated)
 *   - Grand total
 *
 * We don't actually upload the PDF anywhere — the operator downloads
 * it locally and attaches manually. (A future iteration could mint a
 * signed short-lived PDF link.)
 */
function SendToBuyer({ invoice }: { invoice: AdminInvoice }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const tenant = useAuthStore((s) => s.tenant);

  if (!invoice.buyer_name) {
    // Walk-in: nothing to send to.
    return null;
  }

  // The signed download URL the backend mints when an invoice is
  // FBR-validated. WhatsApp's wa.me deep-link and mailto: URIs can't
  // ATTACH a file — the only way to actually deliver the PDF is to
  // include a link in the message body and let the recipient click.
  // The seller's job becomes "send the link", not "attach the PDF".
  // The link is HMAC-signed and TTL-limited (7 days); anyone with
  // it can download the PDF without an account.
  //
  // When share_url is missing (invoice not yet FBR-validated), the
  // menu shows a hint instead — there's no point sharing a draft.
  const shareUrl = invoice.share_url ?? null;
  const fbrLine = invoice.fbr_invoice_number
    ? `\nFBR No: ${invoice.fbr_invoice_number}`
    : "";
  const total = `Rs. ${Number(invoice.grand_total).toLocaleString("en-PK", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
  const downloadLine = shareUrl ? `\n\nDownload your invoice:\n${shareUrl}` : "";
  const body =
    `Dear ${invoice.buyer_name},\n\n`
    + `Your invoice from ${tenant?.business_name ?? "us"}:\n\n`
    + `Invoice No: ${invoice.local_invoice_number}${fbrLine}\n`
    + `Total: ${total}`
    + downloadLine
    + `\n\nThank you for your business.`;
  const subject = `Invoice ${invoice.local_invoice_number} from ${tenant?.business_name ?? ""}`;

  // Pakistani mobile numbers are typically 03XX-XXXXXXX. wa.me requires
  // the country-code-prefixed digits-only form (923XXXXXXXXX). Strip
  // formatting + replace leading 0 with 92.
  const rawPhone = invoice.buyer_phone ?? "";
  const phoneDigits = rawPhone.replace(/\D/g, "");
  const whatsappPhone = phoneDigits.startsWith("0")
    ? "92" + phoneDigits.slice(1)
    : phoneDigits;
  const waUrl = whatsappPhone
    ? `https://wa.me/${whatsappPhone}?text=${encodeURIComponent(body)}`
    : `https://wa.me/?text=${encodeURIComponent(body)}`;

  const buyerEmail = ""; // Not exposed on Invoice today; future field
  const mailtoUrl = `mailto:${encodeURIComponent(buyerEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  async function copyShareUrl() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // navigator.clipboard fails in non-secure contexts; fall back
      // to a manual prompt so the operator can still grab the URL.
      window.prompt("Copy the share link:", shareUrl);
    }
  }

  return (
    <div className="relative">
      <Button variant="outline" onClick={() => setOpen((o) => !o)}>
        <Send className="mr-1 h-4 w-4" /> Send to buyer
      </Button>
      {open && (
        <>
          {/* Click-outside backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          <div
            className="absolute right-0 z-20 mt-1 w-72 rounded-md border bg-background p-2 shadow-md"
            role="menu"
          >
            {shareUrl ? (
              <>
                <a
                  href={waUrl}
                  target="_blank"
                  rel="noreferrer noopener"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  role="menuitem"
                >
                  <MessageCircle className="h-4 w-4" /> WhatsApp
                </a>
                <a
                  href={mailtoUrl}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  role="menuitem"
                >
                  <Mail className="h-4 w-4" /> Email
                </a>
                <button
                  type="button"
                  onClick={copyShareUrl}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
                  role="menuitem"
                >
                  <FileText className="h-4 w-4" />
                  {copied ? "Copied!" : "Copy download link"}
                </button>
                <p className="mt-1 border-t px-2 pt-2 text-[10px] text-muted-foreground leading-snug">
                  Message includes a secure 7-day download link to the
                  FBR-validated PDF. The recipient clicks the link to
                  open the invoice in their browser.
                </p>
              </>
            ) : (
              <p className="px-2 py-2 text-xs text-muted-foreground leading-snug">
                Send-to-buyer is only available once the invoice is
                validated by FBR. Validate or Submit the invoice
                first.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}


/**
 * "More" overflow menu — collects rarely-clicked actions so the main
 * toolbar stays tight. Closes on outside click or Escape.
 *
 * Each item is either an immediate action (`onSelect`) or — for items
 * that need their own UI (none today; reserved for the future) — a
 * React node to render inline.
 *
 * Returns null when there are zero items so the toolbar doesn't show
 * a useless "More ▾" button (e.g. on credit-note invoices where Add
 * Debit Note is filtered out and Download is the only entry — in
 * that case the parent should still render us; we collapse only when
 * truly empty).
 */
interface MoreActionsItem {
  label: string;
  icon: React.ReactNode;
  onSelect?: () => void;
}

function MoreActionsMenu({ items }: { items: MoreActionsItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <Button
        variant="outline"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        title="More actions"
      >
        <MoreHorizontal className="h-4 w-4" />
        <span className="sr-only">More actions</span>
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-52 rounded-md border bg-background p-1 shadow-md"
        >
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
              onClick={() => {
                setOpen(false);
                it.onSelect?.();
              }}
            >
              {it.icon}
              <span>{it.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


/**
 * FBR Submissions Log — shows every PRAL roundtrip for this invoice in
 * chronological order. The client sees exactly what we sent and what
 * FBR returned, including timing, status code, and error message.
 *
 * Useful for the sales demo: "see, the invoice really went to FBR —
 * here's the trace."
 *
 * The endpoint `/api/fbr/submissions/?invoice=<id>` returns every
 * FbrSubmission row for that invoice; the model is immutable
 * (REVOKE UPDATE/DELETE in apps/fbr/0002), so this is also our
 * legal-retention audit log.
 */
function FbrSubmissionsPanel({ invoiceId }: { invoiceId: string }) {
  const { data, isLoading } = useFbrSubmissions({ invoice: invoiceId });
  const rows = data?.results ?? [];

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">FBR submissions log</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading…</p>
        </CardContent>
      </Card>
    );
  }
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">FBR submissions log</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No FBR roundtrips recorded yet. This invoice hasn't been
            submitted to PRAL.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">
          FBR submissions log{" "}
          <span className="text-muted-foreground font-normal">
            ({rows.length} roundtrip{rows.length === 1 ? "" : "s"})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead className="hidden lg:table-cell">Endpoint</TableHead>
              <TableHead className="hidden xl:table-cell">Env</TableHead>
              <TableHead className="hidden text-right md:table-cell">HTTP</TableHead>
              <TableHead className="text-right">PRAL code</TableHead>
              <TableHead className="hidden text-right xl:table-cell">ms</TableHead>
              <TableHead>FBR no. / error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row: FbrSubmissionRow) => (
              <SubmissionRow key={row.id} row={row} />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function SubmissionRow({ row }: { row: FbrSubmissionRow }) {
  const [open, setOpen] = useState(false);
  // PRAL's success code is "00"; anything else is an error/validation
  // failure. Visually mark with green/red so the client can scan at a
  // glance whether FBR accepted the submission.
  const ok = row.status_code === "00";
  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/40"
        onClick={() => setOpen((v) => !v)}
      >
        <TableCell className="font-mono text-xs">
          {new Date(row.submitted_at).toLocaleString()}
          {/* Endpoint surfaced inline where its column is hidden. */}
          <span className="block text-[11px] text-muted-foreground lg:hidden">
            {row.endpoint}
          </span>
        </TableCell>
        <TableCell className="hidden font-mono text-xs lg:table-cell">{row.endpoint}</TableCell>
        <TableCell className="hidden text-xs xl:table-cell">
          <Badge variant={row.environment === "production" ? "default" : "info"}>
            {row.environment}
          </Badge>
        </TableCell>
        <TableCell className="hidden text-right font-mono text-xs md:table-cell">
          {row.http_status}
        </TableCell>
        <TableCell className="text-right font-mono text-xs">
          <Badge variant={ok ? "success" : "destructive"}>
            {row.status_code || "—"}
          </Badge>
        </TableCell>
        <TableCell className="hidden text-right font-mono text-xs xl:table-cell">
          {row.duration_ms ?? "—"}
        </TableCell>
        <TableCell className="font-mono text-[11px] break-all max-w-[280px]">
          {row.fbr_invoice_number || row.error_message || ""}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30 p-0">
            <div className="grid grid-cols-1 gap-4 p-3 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Request payload
                </div>
                <pre className="overflow-auto rounded-md bg-background p-2 text-[10px] leading-tight max-h-72">
                  {JSON.stringify(row.request_payload, null, 2)}
                </pre>
              </div>
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  PRAL response
                </div>
                <pre className="overflow-auto rounded-md bg-background p-2 text-[10px] leading-tight max-h-72">
                  {JSON.stringify(row.response_payload, null, 2)}
                </pre>
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
