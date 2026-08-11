/**
 * Users / Cashiers — tenant staff management (owner + manager).
 *
 * Add staff, edit role / branches / active state, remove them from this
 * business, and set/reset the 6-digit terminal PIN. A cashier logs into a
 * terminal with their PIN; they can work any till in a branch they're assigned
 * to (empty branches = all branches). Server enforces the real permissions
 * (owner-only owner management, last-owner guard, self-lockout) — this UI
 * mirrors them and surfaces the server's messages.
 */
import { KeyRound, Pencil, Plus, Search, Trash2, UserX, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/feedback/Toast";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranchOptions,
  useCreateStaff,
  useDeleteStaff,
  useSetStaffPin,
  useStaff,
  useUpdateStaff,
  type CreateStaffBody,
} from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";
import type { BranchOption, Role, StaffMember } from "@pos/shared/types";

const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  manager: "Manager",
  cashier: "Cashier",
  accountant: "Accountant",
  auditor: "Auditor",
};

export default function UsersList() {
  const myUserId = useAuthStore((s) => s.user?.id);
  const myRole = useAuthStore((s) => s.role);
  const isManager = myRole === "manager"; // manager can't touch owners

  const [search, setSearch] = useState("");
  const { data, isLoading } = useStaff(search ? { search } : {});
  const { data: branchOpts = [] } = useBranchOptions();
  const rows = data?.results ?? [];

  return (
    <div className="space-y-6">
      <PageHeader title="Users" subtitle="Cashiers, managers & staff who can use the POS." />

      <AddStaffForm branches={branchOpts} isManager={isManager} />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle>Staff</CardTitle>
          <div className="relative w-64 max-w-full">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Search name or email…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Branches</TableHead>
                <TableHead>PIN</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">Loading…</TableCell></TableRow>
              ) : rows.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">No staff yet. Add your first user above.</TableCell></TableRow>
              ) : (
                rows.map((s) => (
                  <StaffRow
                    key={s.id}
                    staff={s}
                    branches={branchOpts}
                    isSelf={s.user_id === myUserId}
                    lockedOwner={isManager && s.role === "owner"}
                    isManager={isManager}
                  />
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------- Add form ------------------------------- */

function AddStaffForm({ branches, isManager }: { branches: BranchOption[]; isManager: boolean }) {
  const toast = useToast();
  const create = useCreateStaff();
  const [error, setError] = useState<string | null>(null);
  const [v, setV] = useState<CreateStaffBody>({
    email: "", full_name: "", role: "cashier", branch_ids: [], preferred_language: "en", pin: "",
  });

  // Managers can't create owners.
  const roles: Role[] = isManager
    ? ["cashier", "manager", "accountant", "auditor"]
    : ["cashier", "manager", "owner", "accountant", "auditor"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (v.pin && !/^\d{6}$/.test(v.pin)) {
      setError("PIN must be exactly 6 digits.");
      return;
    }
    try {
      await create.mutateAsync({ ...v, pin: v.pin || undefined });
      toast.show({ message: `${v.full_name} added.`, variant: "success" });
      setV({ email: "", full_name: "", role: "cashier", branch_ids: [], preferred_language: "en", pin: "" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Add user</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Full name *">
            <Input value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} required />
          </Field>
          <Field label="Email *">
            <Input type="email" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} required />
          </Field>
          <Field label="Role *">
            <Select value={v.role} onChange={(e) => setV({ ...v, role: e.target.value as Role })}>
              {roles.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
            </Select>
          </Field>
          <Field label="Language">
            <Select value={v.preferred_language} onChange={(e) => setV({ ...v, preferred_language: e.target.value })}>
              <option value="en">English</option>
              <option value="ur">اردو</option>
            </Select>
          </Field>
          <Field label="PIN (6 digits, optional)">
            <Input inputMode="numeric" maxLength={6} value={v.pin ?? ""}
              onChange={(e) => setV({ ...v, pin: e.target.value.replace(/\D/g, "").slice(0, 6) })}
              placeholder="e.g. 123456" />
          </Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <Label className="mb-1 block text-xs font-medium text-muted-foreground">Branches (none = all branches)</Label>
            <BranchChecklist branches={branches} value={v.branch_ids ?? []} onChange={(ids) => setV({ ...v, branch_ids: ids })} />
          </div>
          {error && <div className="sm:col-span-2 lg:col-span-3 text-sm text-destructive">{error}</div>}
          <div className="sm:col-span-2 lg:col-span-3">
            <Button type="submit" disabled={create.isPending}>
              <Plus className="mr-1 h-4 w-4" /> {create.isPending ? "Adding…" : "Add user"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/* -------------------------------- Row ---------------------------------- */

function StaffRow({
  staff, branches, isSelf, lockedOwner, isManager,
}: {
  staff: StaffMember;
  branches: BranchOption[];
  isSelf: boolean;
  lockedOwner: boolean;   // a manager may not act on an owner row
  isManager: boolean;
}) {
  const toast = useToast();
  const update = useUpdateStaff();
  const del = useDeleteStaff();
  const setPin = useSetStaffPin();
  const [mode, setMode] = useState<"view" | "edit" | "pin">("view");

  const branchLabel = useMemo(() => {
    if (!staff.branch_ids?.length) return "All branches";
    const names = staff.branch_ids
      .map((id) => branches.find((b) => b.id === id)?.name ?? "—")
      .filter(Boolean);
    return names.join(", ");
  }, [staff.branch_ids, branches]);

  async function toggleActive() {
    try {
      await update.mutateAsync({ id: staff.id, is_active: !staff.is_active });
      toast.show({ message: staff.is_active ? "User deactivated." : "User reactivated.", variant: "success" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  async function remove() {
    if (!confirm(`Remove ${staff.full_name} from this business? They can be re-added later.`)) return;
    try {
      await del.mutateAsync(staff.id);
      toast.show({ message: `${staff.full_name} removed.`, variant: "info" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  const canAct = !lockedOwner; // manager can't act on owners

  return (
    <>
      <TableRow className={staff.is_active ? "" : "opacity-60"}>
        <TableCell>
          <div className="font-medium">{staff.full_name}</div>
          <div className="text-xs text-muted-foreground">{staff.email}</div>
        </TableCell>
        <TableCell><Badge variant="secondary">{ROLE_LABELS[staff.role]}</Badge></TableCell>
        <TableCell className="max-w-[220px] truncate text-sm" title={branchLabel}>{branchLabel}</TableCell>
        <TableCell>
          <Badge variant={staff.has_pin ? "default" : "outline"}>{staff.has_pin ? "Set" : "None"}</Badge>
        </TableCell>
        <TableCell>
          <Badge variant={staff.is_active ? "default" : "outline"}>{staff.is_active ? "Active" : "Inactive"}</Badge>
        </TableCell>
        <TableCell className="text-sm text-muted-foreground">
          {staff.last_login ? new Date(staff.last_login).toLocaleDateString() : "—"}
        </TableCell>
        <TableCell className="text-right">
          <div className="flex justify-end gap-1">
            {canAct && (
              <Button size="icon" variant="ghost" title="Edit" onClick={() => setMode(mode === "edit" ? "view" : "edit")}>
                <Pencil className="h-4 w-4" />
              </Button>
            )}
            {canAct && (
              <Button size="icon" variant="ghost" title="Set PIN" onClick={() => setMode(mode === "pin" ? "view" : "pin")}>
                <KeyRound className="h-4 w-4" />
              </Button>
            )}
            {canAct && !isSelf && (
              <Button size="icon" variant="ghost" title={staff.is_active ? "Deactivate" : "Reactivate"} onClick={toggleActive} disabled={update.isPending}>
                <UserX className="h-4 w-4" />
              </Button>
            )}
            {canAct && !isSelf && (
              <Button size="icon" variant="ghost" title="Remove" onClick={remove} disabled={del.isPending}>
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>

      {mode === "edit" && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/40">
            <EditStaff staff={staff} branches={branches} isManager={isManager} onDone={() => setMode("view")} />
          </TableCell>
        </TableRow>
      )}
      {mode === "pin" && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/40">
            <SetPinInline
              onSave={async (pin) => {
                try {
                  await setPin.mutateAsync({ id: staff.id, pin });
                  toast.show({ message: "PIN updated.", variant: "success" });
                  setMode("view");
                } catch (err) {
                  toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
                }
              }}
              busy={setPin.isPending}
              onCancel={() => setMode("view")}
            />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/* ------------------------------ Editors -------------------------------- */

function EditStaff({
  staff, branches, isManager, onDone,
}: { staff: StaffMember; branches: BranchOption[]; isManager: boolean; onDone: () => void }) {
  const toast = useToast();
  const update = useUpdateStaff();
  const [full_name, setName] = useState(staff.full_name);
  const [role, setRole] = useState<Role>(staff.role);
  const [preferred_language, setLang] = useState(staff.preferred_language);
  const [branch_ids, setBranchIds] = useState<string[]>(staff.branch_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  const roles: Role[] = isManager
    ? ["cashier", "manager", "accountant", "auditor"]
    : ["cashier", "manager", "owner", "accountant", "auditor"];

  async function save() {
    setError(null);
    try {
      await update.mutateAsync({ id: staff.id, full_name, role, preferred_language, branch_ids });
      toast.show({ message: "User updated.", variant: "success" });
      onDone();
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="grid gap-3 p-2 sm:grid-cols-2 lg:grid-cols-3">
      <Field label="Full name"><Input value={full_name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Role">
        <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {roles.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </Select>
      </Field>
      <Field label="Language">
        <Select value={preferred_language} onChange={(e) => setLang(e.target.value as "en" | "ur")}>
          <option value="en">English</option>
          <option value="ur">اردو</option>
        </Select>
      </Field>
      <div className="sm:col-span-2 lg:col-span-3">
        <Label className="mb-1 block text-xs font-medium text-muted-foreground">Branches (none = all)</Label>
        <BranchChecklist branches={branches} value={branch_ids} onChange={setBranchIds} />
      </div>
      {error && <div className="sm:col-span-2 lg:col-span-3 text-sm text-destructive">{error}</div>}
      <div className="sm:col-span-2 lg:col-span-3 flex gap-2">
        <Button size="sm" onClick={save} disabled={update.isPending}>{update.isPending ? "Saving…" : "Save changes"}</Button>
        <Button size="sm" variant="outline" onClick={onDone}><X className="mr-1 h-4 w-4" /> Cancel</Button>
      </div>
    </div>
  );
}

function SetPinInline({ onSave, onCancel, busy }: { onSave: (pin: string) => void; onCancel: () => void; busy: boolean }) {
  const [pin, setPin] = useState("");
  const valid = /^\d{6}$/.test(pin);
  return (
    <div className="flex flex-wrap items-end gap-2 p-2">
      <Field label="New 6-digit PIN">
        <Input inputMode="numeric" maxLength={6} value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="123456" className="w-40" />
      </Field>
      <Button size="sm" onClick={() => onSave(pin)} disabled={!valid || busy}>{busy ? "Saving…" : "Set PIN"}</Button>
      <Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button>
    </div>
  );
}

/* ------------------------- Branch multi-select ------------------------- */

function BranchChecklist({
  branches, value, onChange,
}: { branches: BranchOption[]; value: string[]; onChange: (ids: string[]) => void }) {
  if (branches.length === 0) {
    return <div className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">No branches yet.</div>;
  }
  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  }
  return (
    <div className="flex flex-wrap gap-2 rounded-md border p-2">
      {branches.map((b) => {
        const on = value.includes(b.id);
        return (
          <button
            key={b.id}
            type="button"
            onClick={() => toggle(b.id)}
            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            {on ? "✓ " : ""}{b.name}
          </button>
        );
      })}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
