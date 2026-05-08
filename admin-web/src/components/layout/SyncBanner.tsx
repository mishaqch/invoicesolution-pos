import { AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";

import { useSyncStatus } from "@/lib/queries";

export function SyncBanner() {
  const { data } = useSyncStatus();
  const totalFailed = (data?.results ?? []).reduce((acc, r) => acc + r.failed, 0);
  if (totalFailed === 0) return null;

  return (
    <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-900">
      <AlertTriangle className="h-4 w-4" />
      <span>
        {totalFailed} sync {totalFailed === 1 ? "row has" : "rows have"} failed.
      </span>
      <Link
        to="/sync"
        className="ml-auto rounded-md border border-red-300 bg-background px-2 py-0.5 text-xs hover:bg-red-100"
      >
        Review
      </Link>
    </div>
  );
}
