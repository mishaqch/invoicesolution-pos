"""Tenant signals — Phase 5 adds: TenantSettings created on Tenant create."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Tenant, TenantSettings


@receiver(post_save, sender=Tenant)
def seed_default_settings(sender, instance: Tenant, created: bool, **kwargs):
    if not created:
        return
    if hasattr(instance, "settings"):
        return
    TenantSettings.objects.create(
        tenant=instance,
        enabled_payment_methods=["cash"],  # safe default
    )
