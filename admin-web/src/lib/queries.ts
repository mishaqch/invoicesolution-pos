import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  Branch, Category, HsCode, PosProduct, Product,
  StockAudit, StockLevel, StockMovement, StockTransfer,
  TaxRate, UnitOfMeasure,
} from "@pos/shared/types";

import { api } from "./api";

interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ----- Catalog -----
export function useUoms() {
  return useQuery({
    queryKey: ["uoms"],
    queryFn: () => api<UnitOfMeasure[]>("/catalog/uoms/"),
    staleTime: 1000 * 60 * 60,
  });
}

export function useTaxRates() {
  return useQuery({
    queryKey: ["tax-rates"],
    queryFn: () => api<Page<TaxRate>>("/catalog/tax-rates/"),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Page<Category>>("/catalog/categories/?page_size=200"),
  });
}

export function useProducts(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => api<Page<Product>>(`/catalog/products/${query ? `?${query}` : ""}`),
  });
}

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: ["product", id],
    queryFn: () => api<Product>(`/catalog/products/${id}/`),
    enabled: !!id,
  });
}

export function useHsCodes(query: string) {
  return useQuery({
    queryKey: ["hs-codes", query],
    queryFn: () =>
      api<Page<HsCode>>(`/catalog/hs-codes/${query ? `?search=${encodeURIComponent(query)}` : ""}`),
    placeholderData: (prev) => prev,
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Product>) =>
      api<Product>("/catalog/products/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Product> & { id: string }) =>
      api<Product>(`/catalog/products/${id}/`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["product", data.id] });
    },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/catalog/products/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });
}

// ----- Branches -----
export function useBranches() {
  return useQuery({
    queryKey: ["branches"],
    queryFn: () => api<Page<Branch>>("/branches/"),
  });
}

export function useCreateBranch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Branch>) =>
      api<Branch>("/branches/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["branches"] }),
  });
}

// ----- Inventory -----
export function useStockLevels(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["stock-levels", params],
    queryFn: () => api<Page<StockLevel>>(`/inventory/stock-levels/${query ? `?${query}` : ""}`),
  });
}

export function useStockMovements(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["movements", params],
    queryFn: () => api<Page<StockMovement>>(`/inventory/movements/${query ? `?${query}` : ""}`),
  });
}

export function usePostAdjustment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      branch: string; product: string; variant?: string | null;
      quantity: string; movement_type: string; reason: string;
    }) =>
      api<StockMovement>("/inventory/adjustments/", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stock-levels"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
    },
  });
}

export function useTransfers() {
  return useQuery({
    queryKey: ["transfers"],
    queryFn: () => api<Page<StockTransfer>>("/inventory/transfers/"),
  });
}

export function useAudits() {
  return useQuery({
    queryKey: ["audits"],
    queryFn: () => api<Page<StockAudit>>("/inventory/audits/"),
  });
}

export type { Branch, Category, HsCode, PosProduct, Product, TaxRate, UnitOfMeasure };
