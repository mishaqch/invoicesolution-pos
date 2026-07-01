import { DoorOpen, Plus } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import { useBranches, useDeleteRoom, useRooms, useSaveRoom } from "@/lib/queries";
import { money } from "@/lib/utils";

import type { Room } from "@pos/shared/types";

function rows<T>(d: { results: T[] } | T[] | undefined): T[] {
  if (!d) return [];
  return Array.isArray(d) ? d : d.results;
}

const STATUS_STYLES: Record<string, string> = {
  available: "bg-primary-soft text-primary-soft-foreground",
  occupied: "bg-amber-100 text-amber-800",
  maintenance: "bg-slate-200 text-slate-700",
};

export default function RoomsAdmin() {
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];
  const { data, isLoading } = useRooms();
  const del = useDeleteRoom();
  const roomRows = rows<Room>(data);
  const [editing, setEditing] = useState<Room | "new" | null>(null);

  const occupied = roomRows.filter((r) => r.status === "occupied").length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Rooms"
        subtitle={`Bookable rooms and their nightly rates. ${roomRows.length} rooms · ${occupied} occupied.`}
        actions={
          <Button onClick={() => setEditing("new")} className="gap-1">
            <Plus className="h-4 w-4" /> New room
          </Button>
        }
      />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Room</TableHead>
              <TableHead>Type</TableHead>
              <TableHead className="text-right">Base / night</TableHead>
              <TableHead className="text-right">Tax / night</TableHead>
              <TableHead className="text-right">Total / night</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">Loading…</TableCell>
              </TableRow>
            ) : roomRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  <DoorOpen className="mx-auto mb-2 h-6 w-6 opacity-50" />
                  No rooms yet. Add your first room.
                </TableCell>
              </TableRow>
            ) : (
              roomRows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.room_number}</TableCell>
                  <TableCell>{r.room_type}</TableCell>
                  <TableCell className="text-right font-mono">{money(r.nightly_base)}</TableCell>
                  <TableCell className="text-right font-mono">{money(r.nightly_tax)}</TableCell>
                  <TableCell className="text-right font-mono font-semibold">{money(r.nightly_total)}</TableCell>
                  <TableCell>
                    <Badge className={STATUS_STYLES[r.status] ?? ""}>{r.status}</Badge>
                  </TableCell>
                  <TableCell className="space-x-2 text-right">
                    <Button size="sm" variant="outline" onClick={() => setEditing(r)}>Edit</Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={r.status === "occupied"}
                      title={r.status === "occupied" ? "Room is occupied" : "Delete room"}
                      onClick={() => {
                        if (confirm(`Delete room ${r.room_number}?`)) del.mutate(r.id);
                      }}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {editing && (
        <RoomForm
          room={editing === "new" ? null : editing}
          branches={branches}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function RoomForm({
  room,
  branches,
  onClose,
}: {
  room: Room | null;
  branches: { id: string; name: string }[];
  onClose: () => void;
}) {
  const save = useSaveRoom();
  const [roomNumber, setRoomNumber] = useState(room?.room_number ?? "");
  const [roomType, setRoomType] = useState(room?.room_type ?? "");
  const [base, setBase] = useState(String(room?.nightly_base ?? ""));
  const [tax, setTax] = useState(String(room?.nightly_tax ?? "0"));
  const [branch, setBranch] = useState(room?.branch ?? branches[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);

  const total = (Number(base) || 0) + (Number(tax) || 0);

  async function submit() {
    setError(null);
    if (!roomNumber.trim()) return setError("Room number is required.");
    if (!roomType.trim()) return setError("Room type is required.");
    if (!branch) return setError("Pick a branch.");
    try {
      await save.mutateAsync({
        id: room?.id,
        room_number: roomNumber.trim(),
        room_type: roomType.trim(),
        nightly_base: base || "0",
        nightly_tax: tax || "0",
        branch,
      });
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <CardHeader>
          <CardTitle>{room ? "Edit room" : "New room"}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Room number" id="r_num">
              <Input id="r_num" value={roomNumber} onChange={(e) => setRoomNumber(e.target.value)} placeholder="VIP-1" />
            </Field>
            <Field label="Room type" id="r_type">
              <Input id="r_type" value={roomType} onChange={(e) => setRoomType(e.target.value)} placeholder="VIP" />
            </Field>
            <Field label="Base / night (Rs)" id="r_base">
              <NumberInput id="r_base" mode="decimal" value={base} onChange={setBase} />
            </Field>
            <Field label="Tax / night (Rs, fixed)" id="r_tax">
              <NumberInput id="r_tax" mode="decimal" value={tax} onChange={setTax} />
            </Field>
          </div>
          <div className="rounded-md bg-muted/50 px-3 py-2 text-sm">
            Total per night: <span className="font-mono font-semibold">Rs {money(total)}</span>
          </div>
          {branches.length > 1 && (
            <Field label="Branch" id="r_branch">
              <Select id="r_branch" value={branch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </Select>
            </Field>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button loading={save.isPending} onClick={submit}>{room ? "Save" : "Create"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
