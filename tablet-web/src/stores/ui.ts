import { create } from "zustand";

/** Ephemeral UI state (not persisted). */
interface UiState {
  activeCategory: string | null;
  searchQuery: string;
  sheetOpen: boolean; // portrait order bottom-sheet
  tablePickerOpen: boolean;
  modifierProductId: string | null; // which product's modifier sheet is open

  setActiveCategory: (id: string | null) => void;
  setSearchQuery: (q: string) => void;
  setSheetOpen: (open: boolean) => void;
  setTablePickerOpen: (open: boolean) => void;
  setModifierProductId: (id: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeCategory: null,
  searchQuery: "",
  sheetOpen: false,
  tablePickerOpen: false,
  modifierProductId: null,

  setActiveCategory: (id) => set({ activeCategory: id }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setSheetOpen: (open) => set({ sheetOpen: open }),
  setTablePickerOpen: (open) => set({ tablePickerOpen: open }),
  setModifierProductId: (id) => set({ modifierProductId: id }),
}));
