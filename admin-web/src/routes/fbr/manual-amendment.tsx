import { ExternalLink } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ManualAmendmentPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Manual amendment escape hatch</h1>
      <p className="text-sm text-muted-foreground">
        For invoices that missed the 72-hour edit window — neither edits nor
        cancellations are allowed through this app or PRAL's API. The change
        must be made manually in IRIS.
      </p>

      <Card>
        <CardHeader><CardTitle className="text-sm">Steps</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ol className="list-decimal space-y-2 pl-6">
            <li>
              Log into the IRIS portal at{" "}
              <a
                href="https://iris.fbr.gov.pk"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center underline-offset-2 hover:underline"
              >
                iris.fbr.gov.pk <ExternalLink className="ml-0.5 h-3 w-3" />
              </a>
              .
            </li>
            <li>
              Navigate to <em>Sales Tax → Returns → Annexure-C</em> for the
              relevant tax period.
            </li>
            <li>
              Locate the affected invoice by its FBR Invoice Number (visible on
              the invoice detail in this app).
            </li>
            <li>
              Make the correction directly in IRIS. PRAL does not expose a
              programmatic API for this flow.
            </li>
            <li>
              Once submitted in IRIS, mark the invoice as <em>finalized</em> in
              this app so it stops appearing in editable lists.
            </li>
          </ol>
          <p className="text-xs text-muted-foreground">
            We provide guidance but not automation here — the FBR system is
            the source of truth for amendments past the 72-hour window.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
