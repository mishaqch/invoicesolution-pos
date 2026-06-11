import {
  DndContext,
  PointerSensor,
  closestCenter,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, GripVertical, Pencil, Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useCategories } from "@/lib/queries";

import type { Category } from "@pos/shared/types";

interface TreeNode extends Category {
  children: TreeNode[];
  depth: number;
}

/** Build a nested tree from the flat category list. */
function buildTree(rows: Category[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  for (const r of rows) byId.set(r.id, { ...r, children: [], depth: 0 });
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    if (node.parent && byId.has(node.parent)) {
      const parent = byId.get(node.parent)!;
      node.depth = parent.depth + 1;
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sortChildren = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
    nodes.forEach((n) => {
      n.children.forEach((c) => (c.depth = n.depth + 1));
      sortChildren(n.children);
    });
  };
  sortChildren(roots);
  return roots;
}

/** Flatten a tree depth-first, respecting the collapsed set. */
function flatten(tree: TreeNode[], collapsed: Set<string>): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) {
      out.push(n);
      if (!collapsed.has(n.id)) walk(n.children);
    }
  };
  walk(tree);
  return out;
}

/** True if `candidateAncestorId` lives anywhere under `node`. */
function isDescendant(node: TreeNode, candidateAncestorId: string): boolean {
  for (const c of node.children) {
    if (c.id === candidateAncestorId) return true;
    if (isDescendant(c, candidateAncestorId)) return true;
  }
  return false;
}


// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CategoriesList() {
  const { data, isLoading } = useCategories();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const tree = useMemo(() => buildTree(data?.results ?? []), [data?.results]);
  const flat = useMemo(() => flatten(tree, collapsed), [tree, collapsed]);

  const sensors = useSensors(useSensor(PointerSensor, {
    activationConstraint: { distance: 5 },
  }));

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const slug = name.trim().toLowerCase().replace(/\s+/g, "-").slice(0, 64);
      await api("/catalog/categories/", {
        method: "POST",
        body: JSON.stringify({ name, slug, parent: parent || null }),
      });
      setName("");
      setParent("");
      qc.invalidateQueries({ queryKey: ["categories"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function reparent(draggedId: string, newParentId: string | null) {
    setError(null);
    try {
      await api(`/catalog/categories/${draggedId}/`, {
        method: "PATCH",
        body: JSON.stringify({ parent: newParentId }),
      });
      qc.invalidateQueries({ queryKey: ["categories"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reparent failed");
    }
  }

  async function rename(id: string, newName: string) {
    setError(null);
    const trimmed = newName.trim();
    if (!trimmed) {
      setError("Category name is required.");
      return;
    }
    try {
      await api(`/catalog/categories/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed }),
      });
      qc.invalidateQueries({ queryKey: ["categories"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function remove(node: TreeNode) {
    setError(null);
    const childCount = node.children.length;
    const msg = childCount > 0
      ? `Delete "${node.name}" and re-parent its ${childCount} child categor${childCount === 1 ? "y" : "ies"} to top level?`
      : `Delete "${node.name}"?`;
    if (!window.confirm(msg)) return;
    try {
      await api(`/catalog/categories/${node.id}/`, { method: "DELETE" });
      qc.invalidateQueries({ queryKey: ["categories"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const draggedId = String(active.id);
    const overId = String(over.id);
    if (draggedId === overId) return;

    if (overId === "TOP") {
      const dragged = flat.find((n) => n.id === draggedId);
      if (dragged && dragged.parent !== null) void reparent(draggedId, null);
      return;
    }

    const dragged = flat.find((n) => n.id === draggedId);
    if (!dragged) return;
    if (isDescendant(dragged, overId)) {
      setError("Cannot move a category under one of its own descendants.");
      return;
    }
    if (dragged.parent === overId) return;
    void reparent(draggedId, overId);
  }

  function toggle(id: string) {
    setCollapsed((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Categories"
        subtitle="Drag a row onto another to make it a child. Drag onto the top-level drop zone to promote a category to root."
      />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={add} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="parent">Parent</Label>
              <Select id="parent" value={parent} onChange={(e) => setParent(e.target.value)}>
                <option value="">— Top level —</option>
                {data?.results.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </div>
            <Button type="submit" disabled={busy}>
              <Plus className="mr-2 h-4 w-4" /> Add
            </Button>
          </form>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <DndContext
        sensors={sensors}
        modifiers={[restrictToVerticalAxis]}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <p className="p-6 text-sm text-muted-foreground">Loading…</p>
            ) : flat.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">
                No categories yet. Add the first one above.
              </p>
            ) : (
              <>
                <TopLevelDropZone />
                <ul className="divide-y">
                  {flat.map((node) => (
                    <CategoryRow
                      key={node.id}
                      node={node}
                      collapsed={collapsed.has(node.id)}
                      onToggle={() => toggle(node.id)}
                      onRename={(name) => rename(node.id, name)}
                      onDelete={() => remove(node)}
                    />
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>
      </DndContext>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Row + drop zone components
// ---------------------------------------------------------------------------

function CategoryRow({
  node, collapsed, onToggle, onRename, onDelete,
}: {
  node: TreeNode;
  collapsed: boolean;
  onToggle: () => void;
  onRename: (newName: string) => void | Promise<void>;
  onDelete: () => void | Promise<void>;
}) {
  const draggable = useDraggable({ id: node.id });
  const droppable = useDroppable({ id: node.id });
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(node.name);

  const style = draggable.transform
    ? {
        transform: `translate3d(${draggable.transform.x}px, ${draggable.transform.y}px, 0)`,
        opacity: 0.7,
      }
    : undefined;

  function startEdit() {
    setDraftName(node.name);
    setEditing(true);
  }

  function cancelEdit() {
    setDraftName(node.name);
    setEditing(false);
  }

  async function commitEdit() {
    if (draftName.trim() === node.name) {
      setEditing(false);
      return;
    }
    await onRename(draftName);
    setEditing(false);
  }

  return (
    <li
      ref={(el) => {
        draggable.setNodeRef(el);
        droppable.setNodeRef(el);
      }}
      style={style}
      className={`group flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/30 ${
        droppable.isOver ? "bg-primary/10" : ""
      }`}
    >
      <span style={{ width: `${node.depth * 18}px` }} aria-hidden />

      {node.children.length > 0 ? (
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand" : "Collapse"}
          className="rounded-md p-0.5 hover:bg-muted"
        >
          <ChevronRight
            className={`h-4 w-4 transition-transform ${collapsed ? "" : "rotate-90"}`}
          />
        </button>
      ) : (
        <span className="w-5" aria-hidden />
      )}

      <button
        type="button"
        {...draggable.listeners}
        {...draggable.attributes}
        className="cursor-grab text-muted-foreground active:cursor-grabbing"
        aria-label="Drag to reparent"
      >
        <GripVertical className="h-4 w-4" />
      </button>

      {editing ? (
        <form
          className="flex flex-1 items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void commitEdit();
          }}
        >
          <Input
            autoFocus
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                cancelEdit();
              }
            }}
            className="h-7 flex-1"
            aria-label="Category name"
          />
          <Button
            type="submit"
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            aria-label="Save"
          >
            <Check className="h-4 w-4 text-emerald-600" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            aria-label="Cancel"
            onClick={cancelEdit}
          >
            <X className="h-4 w-4" />
          </Button>
        </form>
      ) : (
        <>
          <span className="flex-1">
            <span className="font-medium">{node.name}</span>
            {node.children.length > 0 && (
              <span className="ml-2 text-xs text-muted-foreground">
                ({node.children.length})
              </span>
            )}
          </span>
          <span className="font-mono text-xs text-muted-foreground">{node.slug}</span>
          <div className="ml-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0"
              onClick={startEdit}
              aria-label={`Rename ${node.name}`}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={onDelete}
              aria-label={`Delete ${node.name}`}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}
    </li>
  );
}

function TopLevelDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: "TOP" });
  return (
    <div
      ref={setNodeRef}
      className={`border-b px-3 py-2 text-xs uppercase tracking-wider ${
        isOver
          ? "bg-primary/10 text-primary"
          : "bg-muted/40 text-muted-foreground"
      }`}
    >
      Drop here to promote to top level
    </div>
  );
}
