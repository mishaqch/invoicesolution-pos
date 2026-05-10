"""ViewSets for branches + terminals; onboarding-state endpoint."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasRolePerm
from apps.sales.models import Invoice

from .models import Branch, Tenant, Terminal
from .serializers import BranchSerializer, TerminalSerializer


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class BranchViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.filter(deleted_at__isnull=True).order_by("name")
    serializer_class = BranchSerializer
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class TerminalViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Terminal.objects.select_related("branch").order_by("branch__name", "name")
    serializer_class = TerminalSerializer
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class OnboardingStateView(APIView):
    """GET / PATCH the tenant's onboarding wizard progress.

    Also returns derived flags so the admin web can decide whether to
    show the wizard at all without a second roundtrip:

      - has_branch     — at least one Branch row
      - has_terminal   — at least one Terminal row
      - has_product    — at least one Product (Phase 1) — checked lazily
                         to avoid a circular import at module load time
      - has_first_sale — at least one Invoice (any status)

    On every GET, derived flags are mirrored into `onboarding_state` JSON
    (`branch_done`, `terminal_done`, `product_done`, `first_sale_done`).
    This is what the super-admin sees in the Django Tenant admin under
    "Onboarding" — without the mirror, the JSON stayed empty `{}` even
    though the tenant had completed real steps. The mirror is one-way
    and idempotent: derived true → JSON true. PATCH still wins for
    operator overrides (e.g. dismissed_at).
    """

    permission_classes = [IsAuthenticated]

    # Mapping derived-flag → onboarding_state JSON key.
    _DERIVED_TO_STATE_KEY = {
        "has_branch": "branch_done",
        "has_terminal": "terminal_done",
        "has_product": "product_done",
        "has_first_sale": "first_sale_done",
    }

    def _tenant(self, request) -> Tenant:
        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            raise PermissionDenied("Tenant context required.")
        return Tenant.objects.get(pk=tenant_id)

    def get(self, request):
        from apps.catalog.models import Product
        tenant = self._tenant(request)
        derived = {
            "has_branch": Branch.objects.filter(
                tenant=tenant, deleted_at__isnull=True,
            ).exists(),
            "has_terminal": Terminal.objects.filter(tenant=tenant).exists(),
            "has_product": Product.objects.filter(
                tenant=tenant, deleted_at__isnull=True,
            ).exists(),
            "has_first_sale": Invoice.objects.for_tenant(tenant.id).exists(),
        }

        # Mirror derived flags into the JSON so super-admin sees real progress.
        # We only write keys whose state would CHANGE; an explicit operator
        # override (e.g. dismissed_at, or a manually-toggled key) is preserved.
        current = dict(tenant.onboarding_state or {})
        changed = False
        for derived_key, state_key in self._DERIVED_TO_STATE_KEY.items():
            if derived[derived_key] and not current.get(state_key):
                current[state_key] = True
                changed = True
        if changed:
            tenant.onboarding_state = current
            tenant.save(update_fields=["onboarding_state", "updated_at"])

        return Response({"state": current, "derived": derived})

    def patch(self, request):
        tenant = self._tenant(request)
        new_keys = request.data or {}
        if not isinstance(new_keys, dict):
            return Response({"detail": "Body must be a JSON object."}, status=400)
        merged = {**(tenant.onboarding_state or {}), **new_keys}
        tenant.onboarding_state = merged
        tenant.save(update_fields=["onboarding_state", "updated_at"])
        return Response({"state": merged})
