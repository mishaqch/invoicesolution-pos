"""System check: every model with a `tenant` ForeignKey must use TenantScopedManager.

Runs as part of `python manage.py check`. Catches drift the moment someone
adds a new tenant-scoped model and forgets the manager.

Exemptions: `tenant_memberships` (its lifecycle straddles tenants — listing
all of a user's memberships across tenants is a legitimate query) is
allowlisted by name. Add new exemptions sparingly, with a comment explaining
why the cross-tenant query is intentional.
"""

from __future__ import annotations

from django.apps import apps
from django.core.checks import Error, register

from apps.tenants.managers import TenantScopedManager

# (app_label, model_name) — opt out of the manager requirement.
EXEMPT = {
    # TenantMembership: legitimately spans tenants (a single user can list
    # all of their memberships across tenants).
    ("tenants", "tenantmembership"),
    # AuditLog: tenant FK is intentionally nullable so audits survive
    # tenant deletion (legal: a deleted tenant's audit trail is still ours).
    ("audit", "auditlog"),
    # FbrIpWhitelist: tenant FK is nullable — NULL rows are global infra IPs
    # we declared once for our own server (PRAL whitelists the same 1-3 IPs
    # for all tenants).
    ("fbr", "fbripwhitelist"),
    # Subscription: platform-admin (control-plane) model. Has a tenant FK
    # but is NEVER queried in tenant-scoped contexts — only ever from
    # platform-admin views which see all tenants.
    ("platform_admin", "subscription"),
}


@register()
def tenant_scope_check(app_configs, **kwargs):
    errors = []
    for model in apps.get_models():
        if (model._meta.app_label, model._meta.model_name) in EXEMPT:
            continue
        if not _has_tenant_fk(model):
            continue
        if not isinstance(model._default_manager, TenantScopedManager):
            errors.append(
                Error(
                    f"{model._meta.label} has a `tenant` FK but does not use "
                    "TenantScopedManager as its default manager.",
                    hint=(
                        "Inherit from core.models.TenantScopedModel, or set "
                        "`objects = TenantScopedManager()` explicitly."
                    ),
                    obj=model,
                    id="tenants.E001",
                )
            )
    return errors


def _has_tenant_fk(model) -> bool:
    for field in model._meta.get_fields():
        if getattr(field, "name", None) == "tenant" and field.is_relation:
            return True
    return False
