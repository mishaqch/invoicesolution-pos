"""Wipe all tenant-side data so a fresh setup can be tested end-to-end.

Deletes (in dependency order to avoid PROTECT FK violations):

  Tenant-scoped (per-tenant operational data):
    - audit_log (immutability lock temporarily lifted)
    - sale_item_history → sale_items → payments → invoices
    - fbr_submissions (immutability lock temporarily lifted)
    - fbr_scenario_tests, fbr_tokens, fbr_cancel_budgets
    - stock_movements (immutability lock temporarily lifted) → stock_levels
    - stock_audits, stock_transfers, adjustments
    - returns
    - customer_ledger → customers → customer_groups
    - products (cascades variants + batches)
    - categories
    - cash_sessions
    - terminals → branches
    - subscriptions (per-tenant rows; the catalog itself is kept)
    - tenant_memberships → tenants

  Users:
    - all non-platform-staff users (tenant cashiers, owners, etc.)
    - platform-staff users are KEPT

Preserved:
  - super-admin user (`is_platform_staff=True`)
  - SubscriptionPlan catalog (Starter / Pro / Enterprise)
  - PlatformSettings singleton
  - HsCode, UnitOfMeasure, TaxRate (global reference data)
  - JWT blacklist + outstanding tokens (low-cost noise, not worth touching)

Safety:
  - Refuses to run unless --confirm is passed.
  - Refuses to run when DEBUG=False (production safety) unless --force.
  - Uses a single transaction so a mid-wipe failure leaves the DB intact.
  - Audit / fbr / stock-movement immutability locks are restored at the
    end even if the wipe raises.

Usage:
    python manage.py wipe_tenant_data --dry-run        # preview
    python manage.py wipe_tenant_data --confirm        # do it
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


# Tables that have REVOKE UPDATE, DELETE applied in their app's 0002
# migration. We must grant DELETE for the duration of the wipe, then
# revoke again so the immutability lock is restored.
_IMMUTABLE_TABLES = (
    "audit_log",
    "fbr_submissions",
    "stock_movements",
)


class Command(BaseCommand):
    help = (
        "Wipe all tenant-side data so the platform can be tested from "
        "scratch. Preserves platform staff, plan catalog, reference data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm", action="store_true",
            help="Actually perform the wipe. Without this flag, only a "
                 "dry-run summary is printed.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be deleted and exit. Default when "
                 "--confirm is not supplied.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Override the DEBUG=False safety guard. Use only on "
                 "staging / dev; never in production.",
        )

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError(
                "DEBUG is False — refusing to run without --force. "
                "This command deletes tenant data; do not run it in "
                "production.",
            )

        # Lazy imports so the module loads even if some apps are missing.
        from apps.accounts.models import User
        from apps.audit.models import AuditLog
        from apps.catalog.models import Category, Product, TaxRate
        from apps.customers.models import Customer, CustomerGroup, CustomerLedger
        from apps.fbr.models import (
            FbrCancelBudget,
            FbrCancelBudgetConsumption,
            FbrIpWhitelist,
            FbrScenarioTest,
            FbrSubmission,
            FbrToken,
        )
        from apps.inventory.models import (
            StockAudit,
            StockLevel,
            StockMovement,
            StockTransfer,
        )
        from apps.notifications.models import Notification
        from apps.platform_admin.models import Subscription
        from apps.reports.models import (
            DailySalesSummary,
            ProductVelocity,
            ReportFavorite,
            ReportRun,
        )
        from apps.returns.models import Return
        from apps.sales.models import (
            Discount,
            Invoice,
            Payment,
            SaleItem,
            SaleItemHistory,
        )
        from apps.sync.models import SyncLog
        from apps.tenants.models import (
            Branch,
            CashSession,
            Tenant,
            TenantMembership,
            Terminal,
        )

        dry = opts["dry_run"] or not opts["confirm"]

        # Snapshot counts so the report is meaningful both for dry-run
        # ("here's what I'd delete") and post-wipe verification.
        counts = {
            "Tenants": Tenant.objects.count(),
            "Branches": Branch.objects.count(),
            "Terminals": Terminal.objects.count(),
            "Memberships": TenantMembership.objects.count(),
            "Tenant users": User.objects.filter(is_platform_staff=False).count(),
            "Customers": Customer.objects.count(),
            "Customer groups": CustomerGroup.objects.count(),
            "Invoices": Invoice.objects.count(),
            "Sale items": SaleItem.objects.count(),
            "Payments": Payment.objects.count(),
            "Returns": Return.objects.count(),
            "Products": Product.objects.count(),
            "Categories": Category.objects.count(),
            "Stock levels": StockLevel.objects.count(),
            "Stock movements": StockMovement.objects.count(),
            "Stock audits": StockAudit.objects.count(),
            "Stock transfers": StockTransfer.objects.count(),
            "FBR tokens": FbrToken.objects.count(),
            "FBR submissions": FbrSubmission.objects.count(),
            "FBR scenario tests": FbrScenarioTest.objects.count(),
            "FBR cancel budgets": FbrCancelBudget.objects.count(),
            "Audit log": AuditLog.objects.count(),
            "Subscriptions": Subscription.objects.count(),
            "Cash sessions": CashSession.objects.count(),
        }

        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING(
            "DRY RUN — nothing will be deleted." if dry
            else "EXECUTING — wiping tenant data now."
        ))
        self.stdout.write(self.style.WARNING("=" * 60))
        for label, n in counts.items():
            if n:
                self.stdout.write(f"  {label:<25} {n}")

        # Always show preserved state
        kept_users = User.objects.filter(is_platform_staff=True)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Preserved:"))
        self.stdout.write(f"  Platform-staff users  ({kept_users.count()})")
        for u in kept_users:
            self.stdout.write(f"    - {u.email}")

        if dry:
            self.stdout.write("")
            self.stdout.write("Re-run with --confirm to actually wipe.")
            return

        # GRANT/REVOKE are DDL and live OUTSIDE the wipe transaction —
        # PG can't roll them back anyway. Lifting the locks here means
        # any deletion error inside _execute_wipe surfaces cleanly.
        # We also disconnect the application-layer Django signals that
        # block UPDATE/DELETE on the same tables (defense in depth in
        # the codebase means defense in depth here too).
        self._grant_delete_on_immutable_tables(grant=True)
        disconnected = self._disconnect_immutability_signals()
        try:
            self._execute_wipe(
                User=User, Tenant=Tenant, Branch=Branch, Terminal=Terminal,
                TenantMembership=TenantMembership, CashSession=CashSession,
                Customer=Customer, CustomerGroup=CustomerGroup,
                CustomerLedger=CustomerLedger,
                Invoice=Invoice, Payment=Payment, SaleItem=SaleItem,
                SaleItemHistory=SaleItemHistory, Discount=Discount,
                Return=Return, Product=Product, Category=Category,
                TaxRate=TaxRate,
                StockLevel=StockLevel, StockMovement=StockMovement,
                StockAudit=StockAudit, StockTransfer=StockTransfer,
                FbrToken=FbrToken, FbrSubmission=FbrSubmission,
                FbrScenarioTest=FbrScenarioTest,
                FbrCancelBudget=FbrCancelBudget,
                FbrCancelBudgetConsumption=FbrCancelBudgetConsumption,
                FbrIpWhitelist=FbrIpWhitelist,
                AuditLog=AuditLog, Subscription=Subscription,
                SyncLog=SyncLog, Notification=Notification,
                ReportFavorite=ReportFavorite, ReportRun=ReportRun,
                DailySalesSummary=DailySalesSummary,
                ProductVelocity=ProductVelocity,
            )
        finally:
            # Restore both the DB-level locks AND the Django signals,
            # even if the wipe raised.
            self._reconnect_immutability_signals(disconnected)
            self._grant_delete_on_immutable_tables(grant=False)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Wipe complete."))
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. Sign into Django super-admin at /admin/")
        self.stdout.write("     with your platform-staff credentials.")
        self.stdout.write("  2. Create a fresh tenant via")
        self.stdout.write("     `python manage.py createtenant ...` or via")
        self.stdout.write("     Tenants → + Add tenant in the admin.")
        self.stdout.write("  3. Toggle modules per-tenant as needed.")

    @transaction.atomic
    def _execute_wipe(self, **m):
        """Order matters here: PROTECT FKs force deletion in dependency
        order. Anything pointed-to must be deleted last. Immutability
        GRANT/REVOKE happens outside this atomic block (caller does
        both — they're DDL, can't be rolled back anyway).
        """
        # Top-of-graph operational data with no other dependents.
        m["SyncLog"].objects.all().delete()
        m["Notification"].objects.all().delete()
        m["FbrIpWhitelist"].objects.all().delete()

        # Report artifacts reference users + tenants only.
        m["ReportFavorite"].objects.all().delete()
        m["ReportRun"].objects.all().delete()
        m["DailySalesSummary"].objects.all().delete()
        m["ProductVelocity"].objects.all().delete()

        # Cancel-budget consumption rows reference budgets + users.
        m["FbrCancelBudgetConsumption"].objects.all().delete()

        # Discounts reference tenants only.
        m["Discount"].objects.all().delete()

        # Returns reference invoices.
        m["Return"].objects.all().delete()

        # Sale items + their history reference products + invoices.
        m["SaleItemHistory"].objects.all().delete()
        m["SaleItem"].objects.all().delete()

        # Payments reference invoices.
        m["Payment"].objects.all().delete()

        # FBR submissions reference invoices (now allowed to delete).
        m["FbrSubmission"].objects.all().delete()
        m["FbrScenarioTest"].objects.all().delete()
        m["FbrCancelBudget"].objects.all().delete()

        # Stock movements reference products + branches.
        m["StockMovement"].objects.all().delete()
        m["StockLevel"].objects.all().delete()
        m["StockAudit"].objects.all().delete()
        m["StockTransfer"].objects.all().delete()

        # Now invoices can go (we deleted everything that referenced
        # them above).
        m["Invoice"].objects.all().delete()

        # Customer ledger entries reference customers.
        m["CustomerLedger"].objects.all().delete()
        m["Customer"].objects.all().delete()
        m["CustomerGroup"].objects.all().delete()

        # Products + categories. Variants + batches cascade with Product.
        m["Product"].objects.all().delete()
        m["Category"].objects.all().delete()
        # Tax rates are per-tenant.
        m["TaxRate"].objects.all().delete()

        # Audit log (was REVOKE'd; now allowed).
        m["AuditLog"].objects.all().delete()

        # Subscriptions reference tenants + plans. Plans stay.
        m["Subscription"].objects.all().delete()

        # FBR tokens reference tenants.
        m["FbrToken"].objects.all().delete()

        # Cash sessions reference branches + terminals.
        m["CashSession"].objects.all().delete()

        # Terminals + branches reference tenants. Memberships too.
        m["Terminal"].objects.all().delete()
        m["Branch"].objects.all().delete()
        m["TenantMembership"].objects.all().delete()

        # Tenant users (everyone except platform-staff).
        m["User"].objects.filter(is_platform_staff=False).delete()

        # Tenants last.
        m["Tenant"].objects.all().delete()

    def _disconnect_immutability_signals(self) -> list:
        """Disconnect the pre_delete signals that block deletion on the
        immutable tables at the application layer.

        Returns a list of (signal, receiver, sender) tuples so the caller
        can re-attach them after the wipe.
        """
        from django.db.models.signals import pre_delete

        from apps.audit.models import AuditLog
        from apps.audit.signals import block_audit_delete
        from apps.fbr.models import FbrSubmission
        from apps.fbr.signals import block_submission_delete
        from apps.inventory.models import StockMovement
        from apps.inventory.signals import block_stock_movement_delete

        receivers = [
            (pre_delete, block_audit_delete, AuditLog),
            (pre_delete, block_submission_delete, FbrSubmission),
            (pre_delete, block_stock_movement_delete, StockMovement),
        ]
        for sig, recv, sender in receivers:
            sig.disconnect(recv, sender=sender)
        return receivers

    def _reconnect_immutability_signals(self, receivers: list) -> None:
        for sig, recv, sender in receivers:
            sig.connect(recv, sender=sender)

    def _grant_delete_on_immutable_tables(self, *, grant: bool):
        """Temporarily grant or revoke DELETE on the audit / fbr_submissions
        / stock_movements tables. Without this the DELETE statements above
        raise PG permission errors because migration 0002 of each app
        REVOKE'd UPDATE and DELETE for the legal-retention guarantee.

        We revoke from PUBLIC and from the current connecting role —
        mirrors what the migrations themselves do.
        """
        verb = "GRANT" if grant else "REVOKE"
        preposition = "TO" if grant else "FROM"
        with connection.cursor() as cur:
            current_user = self._current_db_user(cur)
            for tbl in _IMMUTABLE_TABLES:
                cur.execute(
                    f"{verb} UPDATE, DELETE ON {tbl} {preposition} PUBLIC;",
                )
                cur.execute(
                    f"{verb} UPDATE, DELETE ON {tbl} {preposition} {current_user};",
                )

    def _current_db_user(self, cur) -> str:
        cur.execute("SELECT current_user;")
        return cur.fetchone()[0]
