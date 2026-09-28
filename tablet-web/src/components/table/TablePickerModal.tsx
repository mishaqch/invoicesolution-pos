import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getFloor } from "@/api/restaurant";
import { extractApiErrorMessage } from "@/lib/api";
import { TableTile } from "@/components/table/TableTile";
import type { FloorResponse, FloorTable } from "@/types";

interface Props {
  branchId: string;
  currentTableId: string | null;
  onSelect: (table: FloorTable) => void;
  onClose: () => void;
}

/** Table picker modal — grouped by zone, showing occupancy from the floor. */
export function TablePickerModal({ branchId, currentTableId, onSelect, onClose }: Props) {
  const [zone, setZone] = useState<string>("All");

  const floorQuery = useQuery<FloorResponse>({
    queryKey: ["floor", branchId],
    queryFn: () => getFloor(branchId),
    enabled: !!branchId,
  });

  // Close on Escape.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tables = useMemo(() => floorQuery.data?.tables ?? [], [floorQuery.data]);
  const zones = useMemo(() => {
    const set = new Set<string>();
    for (const t of tables) if (t.zone) set.add(t.zone);
    return ["All", ...Array.from(set)];
  }, [tables]);

  const filtered = zone === "All" ? tables : tables.filter((t) => t.zone === zone);

  return (
    <div
      className="modal-scrim"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="tp-title">
        <div className="modal-head">
          <div>
            <h2 id="tp-title">Choose a table</h2>
            <p>Pick where this order is served. Occupied tables show their open order.</p>
          </div>
          <button className="modal-x" type="button" aria-label="Close" onClick={onClose} />
        </div>

        <div className="zone-tabs" role="tablist" aria-label="Dining zones">
          {zones.map((z) => (
            <button
              key={z}
              type="button"
              role="tab"
              aria-selected={z === zone}
              onClick={() => setZone(z)}
            >
              {z}
            </button>
          ))}
        </div>

        <div className="table-grid">
          {floorQuery.isLoading ? (
            <div style={{ gridColumn: "1 / -1", display: "grid", placeItems: "center", padding: 30 }}>
              <div className="page-spin" role="status" aria-label="Loading tables" />
            </div>
          ) : floorQuery.isError ? (
            <div className="auth-err" role="alert" style={{ gridColumn: "1 / -1" }}>
              {extractApiErrorMessage(floorQuery.error)}
            </div>
          ) : filtered.length === 0 ? (
            <p style={{ gridColumn: "1 / -1", color: "var(--reed)", padding: 20 }}>No tables here.</p>
          ) : (
            filtered.map((t) => (
              <TableTile key={t.id} table={t} mine={t.id === currentTableId} onSelect={onSelect} />
            ))
          )}
        </div>

        <div className="modal-foot">
          <span className="legend">
            <span className="lg free" /> Free <span className="lg occ" /> Occupied{" "}
            <span className="lg mine" /> This order
          </span>
        </div>
      </div>
    </div>
  );
}
