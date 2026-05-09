import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface OnboardingState {
  state: {
    profile_done?: boolean;
    branch_done?: boolean;
    terminal_done?: boolean;
    product_done?: boolean;
    first_sale_done?: boolean;
    dismissed_at?: string;
  };
  derived: {
    has_branch: boolean;
    has_terminal: boolean;
    has_product: boolean;
    has_first_sale: boolean;
  };
}

export function useOnboarding() {
  return useQuery({
    queryKey: ["onboarding"],
    queryFn: () => api<OnboardingState>("/onboarding/"),
    staleTime: 1000 * 30,
  });
}

export function useUpdateOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<OnboardingState["state"]>) =>
      api<{ state: OnboardingState["state"] }>("/onboarding/", {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding"] }),
  });
}

/**
 * Whether the wizard banner should show. Hide if:
 *   - the user has dismissed it
 *   - all onboarding criteria are derived-true (system has its first sale,
 *     a branch, a terminal, and a product — wizard is moot)
 */
export function shouldShowOnboarding(o: OnboardingState | undefined): boolean {
  if (!o) return false;
  if (o.state.dismissed_at) return false;
  const { has_branch, has_terminal, has_product, has_first_sale } = o.derived;
  return !(has_branch && has_terminal && has_product && has_first_sale);
}
