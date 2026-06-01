"""Onboard a new tenant + owner user + membership in one shot.

The Django super-admin UI lets you do this in three separate steps
(Tenant → User → TenantMembership), and forgetting the third step is
a very easy mistake — the user can log in but gets "no active tenant"
in the React app. This command bundles all three so the flow is
atomic + idempotent.

Usage:
    python manage.py createtenant \\
        --business-name "Sheikh General Store" \\
        --ntn 1234567 \\
        --owner-email owner@example.com \\
        --owner-password ChangeMe123

What it does:
    1. Creates (or reuses) the Tenant.
    2. Creates (or reuses) the owner User. is_platform_staff is FALSE.
       is_active is TRUE. Password is hashed.
    3. Creates the TenantMembership with role='owner', is_active=True.
    4. Prints the credentials + the URLs to log in.

Re-runnable: if the tenant or user already exists, the command updates
them in place rather than failing — so it's safe to script.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create a new tenant, an owner user, and the membership linking them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--business-name", required=True,
            help="Trading / legal name shown on invoices.",
        )
        parser.add_argument(
            "--ntn", required=True,
            help="National Tax Number — must be unique. Up to 13 chars.",
        )
        parser.add_argument(
            "--owner-email", required=True,
            help="Email address of the owner user. Used to log in.",
        )
        parser.add_argument(
            "--owner-password", default="ChangeMe123",
            help="Initial password for the owner. Default 'ChangeMe123' — "
                 "owner should change it on first login.",
        )
        parser.add_argument(
            "--business-type",
            choices=["sole_proprietor", "partnership", "private_ltd",
                     "public_ltd", "aop"],
            default="sole_proprietor",
        )
        parser.add_argument(
            "--province",
            choices=["PUNJAB", "SINDH", "KPK", "BALOCHISTAN",
                     "ICT", "GB", "AJK"],
            default="PUNJAB",
        )
        parser.add_argument(
            "--full-name", default="",
            help="Owner's display name (optional).",
        )
        parser.add_argument(
            "--business-mode",
            choices=["pos", "digital_invoicing", "both"],
            default="digital_invoicing",
            help=(
                "Which product the tenant signed up for. "
                "'pos' = counter-side till + inventory + hardware "
                "(required for Tier-1 retailers under FBRIMS). "
                "'digital_invoicing' = back-office invoice tool only "
                "(default — fits service providers, wholesalers, "
                "marriage halls). 'both' = unusual; only when the "
                "customer needs both surfaces. The matching default "
                "module set is applied automatically."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        from apps.accounts.models import User
        from apps.tenants.business_mode import default_modules_for_mode
        from apps.tenants.models import Tenant, TenantMembership
        from apps.tenants.modules import normalise as normalise_modules

        mode = opts["business_mode"]
        # Default modules for the chosen product. Tier-1 retailers
        # (pos) need the full counter set; service providers et al.
        # (digital_invoicing) get a slim back-office set.
        default_modules = normalise_modules(default_modules_for_mode(mode))

        tenant, t_created = Tenant.objects.get_or_create(
            ntn=opts["ntn"],
            defaults={
                "business_name": opts["business_name"],
                "business_type": opts["business_type"],
                "province": opts["province"],
                "business_mode": mode,
                "modules_enabled": default_modules,
            },
        )
        if not t_created:
            # Existing tenant: refresh business_mode + modules to match
            # the supplied flag so re-running this command can be used
            # to flip a tenant from POS to DI (or vice versa) cleanly.
            tenant.business_name = opts["business_name"]
            tenant.business_type = opts["business_type"]
            tenant.province = opts["province"]
            tenant.business_mode = mode
            tenant.modules_enabled = default_modules
            tenant.save()

        if t_created:
            self.stdout.write(self.style.SUCCESS(
                f"✓ Created tenant: {tenant.business_name} (NTN {tenant.ntn})",
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"• Tenant with NTN {tenant.ntn} already existed — updated.",
            ))

        # Owner user — never platform-staff. Always tenant.
        email = opts["owner_email"].strip().lower()
        user, u_created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": opts["full_name"] or email.split("@")[0],
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "is_platform_staff": False,
            },
        )
        if u_created:
            user.set_password(opts["owner_password"])
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"✓ Created user: {user.email}",
            ))
        else:
            if user.is_platform_staff:
                raise CommandError(
                    f"User {email} is a platform-staff account and "
                    f"cannot be assigned as a tenant owner. Pick a "
                    f"different email or clear is_platform_staff first.",
                )
            self.stdout.write(self.style.WARNING(
                f"• User {email} already existed — reusing.",
            ))

        # Membership — idempotent.
        membership, m_created = TenantMembership.objects.get_or_create(
            user=user,
            tenant=tenant,
            defaults={"role": "owner", "is_active": True},
        )
        if not m_created:
            membership.role = "owner"
            membership.is_active = True
            membership.save()
        self.stdout.write(self.style.SUCCESS(
            f"✓ Membership: {user.email} → {tenant.business_name} (owner)",
        ))

        # Hand the operator everything they need to sign in.
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("Tenant onboarded — credentials:"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"  Business:  {tenant.business_name}")
        self.stdout.write(f"  NTN:       {tenant.ntn}")
        self.stdout.write(f"  Mode:      {tenant.business_mode}")
        self.stdout.write(f"  Email:     {user.email}")
        if u_created:
            self.stdout.write(f"  Password:  {opts['owner_password']}")
            self.stdout.write(self.style.WARNING(
                "    ↑ change on first login (initial password)",
            ))
        else:
            self.stdout.write("  Password:  (unchanged — user already existed)")
        self.stdout.write("")
        self.stdout.write("Sign in at:")
        self.stdout.write("  React tenant admin:  http://localhost:5173/")
        self.stdout.write("=" * 60)
