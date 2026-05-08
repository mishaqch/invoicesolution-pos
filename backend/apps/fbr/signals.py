"""Append-only guards for fbr_submissions + fbr_invoice_number immutability.

Same defense-in-depth pattern as audit_log / stock_movements: DB-level
REVOKE/trigger is the truth, signals are the early-warning.
"""

from __future__ import annotations

from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from apps.sales.models import Invoice

from .models import FbrSubmission


class FbrSubmissionImmutableError(PermissionError):
    pass


class FbrInvoiceNumberImmutableError(PermissionError):
    pass


@receiver(pre_save, sender=FbrSubmission)
def block_submission_update(sender, instance: FbrSubmission, **kwargs):
    if instance.pk is not None and FbrSubmission.objects.filter(pk=instance.pk).exists():
        raise FbrSubmissionImmutableError(
            "fbr_submissions is append-only. Insert a new row instead."
        )


@receiver(pre_delete, sender=FbrSubmission)
def block_submission_delete(sender, instance: FbrSubmission, **kwargs):
    raise FbrSubmissionImmutableError("fbr_submissions is append-only. Delete is forbidden.")


@receiver(pre_save, sender=Invoice)
def block_fbr_invoice_number_change(sender, instance: Invoice, **kwargs):
    """Once an invoice has an FBR Invoice Number, that field can never change.

    The Postgres trigger in apps/fbr/migrations/0002 is the authoritative
    enforcement; this signal is the early-warning that catches ORM mistakes.
    """
    if not instance.pk:
        return
    try:
        prior = Invoice.objects.only("fbr_invoice_number").get(pk=instance.pk)
    except Invoice.DoesNotExist:
        return
    if prior.fbr_invoice_number and prior.fbr_invoice_number != instance.fbr_invoice_number:
        raise FbrInvoiceNumberImmutableError(
            f"invoices.fbr_invoice_number is immutable once set "
            f"(was {prior.fbr_invoice_number!r}, attempted {instance.fbr_invoice_number!r})."
        )
