import { Plus, Trash2, Utensils } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { PageHeader } from "@/components/ui/page-header";
import { extractApiErrorMessage } from "@/lib/api";
import { money } from "@/lib/utils";
import {
  useDeleteModifierGroup,
  useModifierGroups,
  useSaveModifierGroup,
  type Modifier,
  type RestaurantModifierGroup,
} from "@/lib/queries";

export default function ModifiersAdmin() {
  const { data, isLoading } = useModifierGroups();
  const del = useDeleteModifierGroup();
  const groups = data?.results ?? [];
  const [editing, setEditing] = useState<RestaurantModifierGroup | "new" | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Modifiers"
        subtitle="Option groups for menu items — sizes, add-ons. Attach them to a product on its edit page."
        actions={
          <Button onClick={() => setEditing("new")} className="gap-1">
            <Plus className="h-4 w-4" /> New group
          </Button>
        }
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : groups.length === 0 ? (
        <div className="rounded-md border py-10 text-center text-muted-foreground">
          <Utensils className="mx-auto mb-2 h-6 w-6 opacity-50" />
          No modifier groups yet. Create one like "Size" or "Add-ons".
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {groups.map((g) => (
            <Card key={g.id}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">
                  {g.name}
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {g.min_select === 0 ? "optional" : "required"} · pick {g.min_select}–{g.max_select}
                  </span>
                </CardTitle>
                <div className="space-x-2">
                  <Button size="sm" variant="outline" onClick={() => setEditing(g)}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => { if (confirm(`Delete "${g.name}"?`)) del.mutate(g.id); }}>Delete</Button>
                </div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  {g.modifiers.map((m) => (
                    <li key={m.id} className="flex justify-between">
                      <span>{m.name}</span>
                      <span className="font-mono text-muted-foreground">
                        {Number(m.price_delta) > 0 ? `+${money(m.price_delta)}` : "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <GroupForm group={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}

function GroupForm({ group, onClose }: { group: RestaurantModifierGroup | null; onClose: () => void }) {
  const save = useSaveModifierGroup();
  const [name, setName] = useState(group?.name ?? "");
  const [minSel, setMinSel] = useState(String(group?.min_select ?? 0));
  const [maxSel, setMaxSel] = useState(String(group?.max_select ?? 1));
  const [mods, setMods] = useState<Modifier[]>(
    group?.modifiers.length
      ? group.modifiers.map((m) => ({ ...m }))
      : [{ name: "", price_delta: "0", display_order: 0, is_active: true }],
  );
  const [error, setError] = useState<string | null>(null);

  function setMod(i: number, patch: Partial<Modifier>) {
    setMods((ms) => ms.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  }

  async function submit() {
    setError(null);
    if (!name.trim()) { setError("Group name is required."); return; }
    const valid = mods.filter((m) => m.name.trim());
    if (valid.length === 0) { setError("Add at least one option."); return; }
    try {
      await save.mutateAsync({
        id: group?.id,
        name: name.trim(),
        min_select: Number(minSel) || 0,
        max_select: Number(maxSel) || 1,
        display_order: group?.display_order ?? 0,
        is_active: true,
        modifiers: valid.map((m, i) => ({
          name: m.name.trim(),
          price_delta: m.price_delta || "0",
          display_order: i,
          is_active: true,
        })),
      });
      onClose();
    } catch (err) { setError(extractApiErrorMessage(err)); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <CardHeader><CardTitle>{group ? "Edit group" : "New modifier group"}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="Group name" id="g_name"><Input id="g_name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Size / Add-ons" /></Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Min select (0 = optional)" id="g_min"><NumberInput id="g_min" mode="integer" value={minSel} onChange={setMinSel} /></Field>
            <Field label="Max select" id="g_max"><NumberInput id="g_max" mode="integer" value={maxSel} onChange={setMaxSel} /></Field>
          </div>
          <div className="space-y-2">
            <Label>Options</Label>
            {mods.map((m, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input value={m.name} onChange={(e) => setMod(i, { name: e.target.value })} placeholder="Large / Extra cheese" />
                <div className="w-32"><NumberInput mode="decimal" value={m.price_delta} onChange={(v) => setMod(i, { price_delta: v })} aria-label="Price delta" /></div>
                <Button type="button" size="icon" variant="ghost" onClick={() => setMods((ms) => ms.filter((_, idx) => idx !== i))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="outline" className="gap-1"
              onClick={() => setMods((ms) => [...ms, { name: "", price_delta: "0", display_order: ms.length, is_active: true }])}>
              <Plus className="h-4 w-4" /> Add option
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button loading={save.isPending} onClick={submit}>{group ? "Save" : "Create"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>;
}
