from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Invoice, InvoiceLine, Payment, PaymentReminder
from .services import apply_payment, recalculate_invoice


@receiver(post_save, sender=Invoice)
def ensure_invoice_reference(sender, instance: Invoice, created: bool, **kwargs):
    if instance.reference:
        return
    Invoice.objects.filter(id=instance.id, reference="").update(
        reference=f"INV-{instance.id:05d}"
    )


@receiver(post_save, sender=Invoice)
def emit_invoice_created_platform_event(
    sender, instance: Invoice, created: bool, **kwargs
):
    """Path-to-10: emit platform event catalog for automation/analytics."""
    if not created:
        return
    try:
        from apps.platform_runtime.events import emit_platform_event

        school_id = getattr(instance, "school_id", None)
        emit_platform_event(
            "invoice_created",
            {"invoice_id": instance.id, "school_id": school_id},
            school_id=school_id,
        )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        import logging

        logging.getLogger(__name__).debug("emit_invoice_created_platform_event: %s", e)


@receiver(post_save, sender=Invoice)
def notify_guardians_new_invoice_signal(
    sender, instance: Invoice, created: bool, **kwargs
):
    """Phase 2.3: In-app (and optional email) notification when a new invoice is issued."""
    if (
        not created
        or not instance.student_id
        or instance.invoice_type != Invoice.InvoiceType.AR
    ):
        return
    try:
        from .notifications import notify_guardians_new_invoice

        notify_guardians_new_invoice(instance, created_by=None)
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        import logging

        logging.getLogger(__name__).debug("notify_guardians_new_invoice_signal: %s", e)


@receiver(post_save, sender=Invoice)
def ensure_payment_reminder(sender, instance: Invoice, created: bool, **kwargs):
    if instance.invoice_type != Invoice.InvoiceType.AR or not instance.due_date:
        return

    reminder, _ = PaymentReminder.objects.get_or_create(invoice=instance)
    reminder.is_active = instance.status not in (
        Invoice.Status.PAID,
        Invoice.Status.VOID,
    )
    reminder.save(update_fields=["is_active"])
    reminder.schedule_next()


@receiver(post_save, sender=InvoiceLine)
def sync_invoice_totals(sender, instance: InvoiceLine, created: bool, **kwargs):
    recalculate_invoice(instance.invoice)


@receiver(post_delete, sender=InvoiceLine)
def sync_invoice_totals_delete(sender, instance: InvoiceLine, **kwargs):
    recalculate_invoice(instance.invoice)


@receiver(post_save, sender=Payment)
def sync_payment(sender, instance: Payment, created: bool, **kwargs):
    if not instance.receipt_number:
        receipt = f"RCPT-{instance.id:05d}"
        Payment.objects.filter(id=instance.id, receipt_number="").update(
            receipt_number=receipt
        )
        instance.receipt_number = receipt
    if instance.invoice_id:
        apply_payment(instance)
    if created and instance.invoice_id:
        try:
            from .notifications import notify_guardians_payment_received

            created_by = getattr(instance, "processed_by", None) or getattr(
                instance, "created_by", None
            )
            notify_guardians_payment_received(instance, created_by=created_by)
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            import logging

            logging.getLogger(__name__).debug(
                "notify_guardians_payment_received signal: %s", e
            )


@receiver(post_delete, sender=Payment)
def sync_payment_delete(sender, instance: Payment, **kwargs):
    if instance.invoice_id:
        recalculate_invoice(instance.invoice)


@receiver(post_save, sender=Payment)
def dispatch_payment_failed_workflows(sender, instance: Payment, **kwargs):
    """Visual / school automation: payment_failed trigger when gateway marks payment failed."""
    if getattr(instance, "status", None) != "failed":
        return
    inv = getattr(instance, "invoice", None)
    school = getattr(instance, "school", None) or (
        getattr(inv, "school", None) if inv else None
    )
    if not school:
        return
    try:
        from apps.siteconfig.workflow_triggers import dispatch_domain_triggers_safe

        dispatch_domain_triggers_safe(
            school,
            "payment_failed",
            {
                "payment_id": instance.pk,
                "invoice_id": getattr(inv, "pk", None) if inv else None,
                "student_id": getattr(instance, "student_id", None)
                or (getattr(inv, "student_id", None) if inv else None),
                "status_reason": (getattr(instance, "status_reason", None) or "")[:500],
            },
        )
    except ImportError:
        pass


def _deactivate_reminders_for_student(student_profile):
    """Deactivate all payment reminders for invoices belonging to this student."""
    PaymentReminder.objects.filter(
        invoice__student=student_profile,
        is_active=True,
    ).update(is_active=False)


def _on_student_inactive_stop_reminders(sender, instance, **kwargs):
    """When a student is marked inactive/withdrawn, stop their payment reminders."""
    if getattr(instance, "is_active", True) is False:
        _deactivate_reminders_for_student(instance)


try:
    from apps.people.models import StudentProfile

    post_save.connect(_on_student_inactive_stop_reminders, sender=StudentProfile)
except ImportError:
    pass
