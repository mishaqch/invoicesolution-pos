"""ViewSets for branches + terminals; onboarding-state endpoint."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasModule, HasRolePerm
from apps.sales.models import Invoice

from .models import Branch, Tenant, Terminal
from .serializers import (
    BranchSerializer,
    TerminalPairSerializer,
    TerminalSerializer,
)


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
    permission_classes = [
        HasModule.for_module("branches"),
        HasRolePerm.with_perm("settings.business_profile"),
    ]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        # Soft-delete: a branch is referenced by immutable audit tables
        # (stock_movements, invoices) whose UPDATE/DELETE is revoked at the DB
        # level for compliance ("audit, don't delete"). A hard delete would
        # trip the FK cascade against those tables. Setting deleted_at hides
        # the branch (the queryset filters deleted_at__isnull=True) while
        # preserving history.
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class TerminalViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Terminal.objects.select_related("branch").order_by("branch__name", "name")
    serializer_class = TerminalSerializer
    permission_classes = [
        HasModule.for_module("terminals"),
        HasRolePerm.with_perm("settings.business_profile"),
    ]

    def perform_create(self, serializer):
        # New terminals are created from admin-web WITHOUT a real device yet,
        # so admin-web doesn't have to invent a device_fingerprint. Stamp a
        # placeholder ("unpaired-<uuid>") that the pairing step overwrites with
        # the machine's real fingerprint. Also auto-issue a pairing code so the
        # owner can hand it to the cashier immediately.
        import uuid as _uuid

        extra = {"tenant_id": self.request.tenant_id}
        if not serializer.validated_data.get("device_fingerprint"):
            extra["device_fingerprint"] = f"unpaired-{_uuid.uuid4().hex}"
        terminal = serializer.save(**extra)
        terminal.issue_pairing_code()

    def perform_destroy(self, instance):
        # Terminals have no deleted_at; deactivate instead of hard-deleting,
        # since invoices reference the terminal (PROTECT) and numbering history
        # must survive. Deactivated terminals stop being usable for sales.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @action(detail=True, methods=["post"], url_path="issue-code")
    def issue_code(self, request, pk=None):
        """Owner re-issues a fresh pairing code for this terminal."""
        terminal = self.get_object()
        code = terminal.issue_pairing_code()
        return Response({
            "pairing_code": code,
            "pairing_code_expires_at": terminal.pairing_code_expires_at,
        })

    @action(
        detail=False, methods=["post"], url_path="pair",
        permission_classes=[AllowAny], authentication_classes=[],
    )
    def pair(self, request):
        """Public: an Electron terminal redeems a one-time pairing code.

        The code is the bearer of trust (single-use, expiring, owner-issued).
        We bind this physical device to the Terminal row and return the branch
        identity the terminal needs to ring sales + fiscalize. We do NOT return
        auth tokens — the cashier logs in separately (email + PIN); device
        identity and cashier identity are intentionally decoupled.
        """
        from django.conf import settings

        ser = TerminalPairSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        code = ser.validated_data["pairing_code"].strip().upper()
        fingerprint = ser.validated_data["device_fingerprint"].strip()

        terminal = (
            Terminal.objects.select_related("branch", "tenant")
            .filter(pairing_code=code, is_active=True)
            .first()
        )
        if terminal is None:
            raise ValidationError({"pairing_code": "Invalid or already-used pairing code."})
        if (
            terminal.pairing_code_expires_at
            and terminal.pairing_code_expires_at < timezone.now()
        ):
            raise ValidationError({"pairing_code": "This pairing code has expired. Ask the owner to re-issue it."})

        # Reject a fingerprint already bound to a DIFFERENT terminal so one
        # physical machine can't masquerade as two terminals (which would break
        # invoice-number monotonicity per terminal).
        clash = (
            Terminal.objects.filter(device_fingerprint=fingerprint)
            .exclude(pk=terminal.pk)
            .first()
        )
        if clash is not None:
            raise ValidationError({
                "device_fingerprint": (
                    "This machine is already paired to another terminal "
                    f"({clash.name}). Unpair it there first."
                ),
            })

        terminal.device_fingerprint = fingerprint
        terminal.os_version = ser.validated_data.get("os_version") or terminal.os_version
        terminal.app_version = ser.validated_data.get("app_version") or terminal.app_version
        terminal.paired_at = timezone.now()
        terminal.last_seen_at = timezone.now()
        # Single-use: burn the code once redeemed.
        terminal.pairing_code = None
        terminal.pairing_code_expires_at = None
        terminal.save(update_fields=[
            "device_fingerprint", "os_version", "app_version",
            "paired_at", "last_seen_at",
            "pairing_code", "pairing_code_expires_at", "updated_at",
        ])

        branch = terminal.branch
        return Response({
            "tenant_id": str(terminal.tenant_id),
            "tenant_name": terminal.tenant.business_name,
            "branch_id": str(branch.id),
            "branch_name": branch.name,
            "branch_code": branch.code,
            "branch_fbr_pos_id": branch.fbr_pos_id,
            "terminal_id": str(terminal.id),
            "terminal_name": terminal.name,
            "terminal_index": terminal.terminal_index,
            # The SDC base URL the terminal should call. Default to its own
            # localhost — the FBR Fiscalization service runs per machine. The
            # terminal can override this in Hardware settings if the branch
            # routes fiscalization through one shared LAN machine instead.
            "sdc_url": getattr(settings, "FBR_SDC_BASE_URL", "") or "http://localhost:8524",
        }, status=status.HTTP_200_OK)


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


class TenantModulesView(APIView):
    """Return which modules are enabled for the current tenant.

    Frontend uses this on app boot to drive sidebar nav visibility and
    route guards. Returns the full catalog (so the UI can render a
    consistent menu structure) plus the enabled-key set so it knows
    which to hide.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .modules import MODULES, is_module_enabled

        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            raise PermissionDenied("Tenant context required.")
        tenant = Tenant.objects.only(
            "modules_enabled", "business_mode", "fbr_connection_type", "vertical",
        ).get(pk=tenant_id)

        return Response({
            "catalog": [
                {
                    "key": m["key"],
                    "label": m["label"],
                    "group": m["group"],
                    "description": m["description"],
                    "forced": m["forced"],
                }
                for m in MODULES
            ],
            "enabled": [
                m["key"] for m in MODULES
                if is_module_enabled(tenant, m["key"])
            ],
            # Drives mode-aware FBR/Branches UI in admin-web:
            #   di_api  -> show PRAL token setup + sandbox scenarios
            #   ims_sdc -> hide them; show only FBR POS ID + connection status
            "business_mode": tenant.business_mode,
            "fbr_connection_type": tenant.fbr_connection_type,
            # Presentation vertical (grocery vs pharmacy) — admin-web surfaces
            # pharmacy-only sections (batch/expiry/suppliers) only for pharmacy.
            "vertical": tenant.vertical,
        })


class TenantSetupView(APIView):
    """Tenant self-serve setup — runs the first-time onboarding wizard.

    GET  /api/tenants/me/setup/   returns the current setup state +
                                  the valid choices for each field so
                                  the wizard can render dropdowns
                                  without hardcoding the lists.

    PATCH /api/tenants/me/setup/  accepts any of:
        - business_mode                 ('pos' | 'digital_invoicing' | 'both')
        - fbr_business_natures          list of FBR_BUSINESS_NATURES strings
        - fbr_sector                    one of FBR_SECTORS
        - apply_default_modules         bool — when true, replaces
                                        `modules_enabled` with the
                                        default set for the chosen
                                        business_mode. Used only by
                                        the onboarding wizard at
                                        first run; after that the
                                        super-admin owns module config.

    Only an active member with the `settings.business_profile` perm
    (owner role today) can PATCH. GET is open to any tenant member.

    Returns the updated state on success.
    """

    permission_classes = [IsAuthenticated]

    def _tenant(self, request):
        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            raise PermissionDenied("Tenant context required.")
        return Tenant.objects.get(pk=tenant_id)

    def get(self, request):
        from .business_mode import (
            BUSINESS_MODES, FBR_BUSINESS_NATURES, FBR_SECTORS,
            LIKELY_SECTOR_FOR_NATURE,
        )
        t = self._tenant(request)
        return Response({
            "business_mode": t.business_mode,
            "fbr_business_natures": list(t.fbr_business_natures or []),
            "fbr_sector": t.fbr_sector,
            "business_name": t.business_name,
            "ntn": t.ntn,
            # Whether the wizard has been completed at least once.
            # The frontend uses this to decide whether to auto-open the
            # wizard on first login.
            "setup_complete": bool(
                t.fbr_business_natures
                and t.fbr_sector
                and t.business_mode
            ),
            "choices": {
                "business_modes": [
                    {"value": v, "label": l} for v, l in BUSINESS_MODES
                ],
                "fbr_business_natures": list(FBR_BUSINESS_NATURES),
                "fbr_sectors": list(FBR_SECTORS),
                # Pre-fill hint: a sane default sector for each nature.
                "likely_sector_for_nature": LIKELY_SECTOR_FOR_NATURE,
            },
        })

    def patch(self, request):
        from .business_mode import (
            BUSINESS_MODES, FBR_BUSINESS_NATURES, FBR_SECTORS,
            default_modules_for_mode,
        )
        from .modules import normalise as normalise_modules

        # Locked down to platform staff only. business_mode and
        # modules_enabled are super-admin concerns now — we ship two
        # products (POS / IMS vs Digital Invoicing) and the tenant
        # gets shaped by the super-admin at provisioning. The
        # SetupWizard that used to live on the tenant side is gone.
        # Tenants who need to switch products contact support.
        if not getattr(request.user, "is_platform_staff", False):
            raise PermissionDenied(
                "Business profile changes are handled by support. "
                "Contact us to switch product type.",
            )

        t = self._tenant(request)
        body = request.data or {}
        update_fields: list[str] = []

        if "business_mode" in body:
            mode = body["business_mode"]
            if mode not in {v for v, _ in BUSINESS_MODES}:
                return Response(
                    {"business_mode": f"Must be one of: "
                     f"{', '.join(v for v, _ in BUSINESS_MODES)}"},
                    status=400,
                )
            t.business_mode = mode
            update_fields.append("business_mode")

        if "fbr_business_natures" in body:
            raw = body["fbr_business_natures"] or []
            if not isinstance(raw, list):
                return Response(
                    {"fbr_business_natures": "Must be a list."},
                    status=400,
                )
            valid = set(FBR_BUSINESS_NATURES)
            bad = [v for v in raw if v not in valid]
            if bad:
                return Response(
                    {"fbr_business_natures":
                        f"Unknown nature(s): {', '.join(bad)}. "
                        f"Valid values: {', '.join(sorted(valid))}"},
                    status=400,
                )
            t.fbr_business_natures = list(raw)
            update_fields.append("fbr_business_natures")

        if "fbr_sector" in body:
            sector = body["fbr_sector"]
            if sector and sector not in FBR_SECTORS:
                return Response(
                    {"fbr_sector": f"Unknown sector. Valid: "
                     f"{', '.join(FBR_SECTORS)}"},
                    status=400,
                )
            t.fbr_sector = sector or None
            update_fields.append("fbr_sector")

        if body.get("apply_default_modules"):
            t.modules_enabled = normalise_modules(
                default_modules_for_mode(t.business_mode),
            )
            update_fields.append("modules_enabled")

        if update_fields:
            update_fields.append("updated_at")
            t.save(update_fields=update_fields)

        # Echo back the GET shape so the client can update without
        # re-fetching.
        return self.get(request)
