import logging

from django.conf import settings
from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Invoice, InvoiceLine, Payment, PaymentReminder
from .services import apply_payment, recalculate_invoice

logger = logging.getLogger(__name__)


def _finance_signals_enabled() -> bool:
    """Tests set SEND_FINANCE_SIGNALS=False to isolate DB constraint / validation paths."""
    return getattr(settings, "SEND_FINANCE_SIGNALS", True)


def _requires_explicit_rls_context() -> bool:
    return connection.vendor == "postgresql" and not getattr(
        settings, "USE_DJANGO_TENANTS", False
    )


def _run_with_optional_school_rls(school_id, runnable, *, operation: str):
    if school_id is None:
        if _requires_explicit_rls_context():
            logger.warning("%s skipped: missing school_id under RLS", operation)
            return 0
        return runnable()
    if _requires_explicit_rls_context():
        from apps.schools.rls_context import rls_school

        with rls_school(school_id):
            return runnable()
    return runnable()


@receiver(post_save, sender=Invoice)
def ensure_invoice_reference(sender, instance: Invoice, created: bool, **kwargs):
    if instance.reference:
        return
    school_id = getattr(instance, "school_id", None)
    # tenant-isolation-allow: signal-handler-scoped-via-instance-school-fk
    queryset = Invoice.objects.filter(id=instance.id, reference="")
    if school_id is not None:
        queryset = queryset.filter(school_id=school_id)
    _run_with_optional_school_rls(
        school_id,
        lambda: queryset.update(reference=f"INV-{instance.id:05d}"),
        operation="ensure_invoice_reference",
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
    if not _finance_signals_enabled():
        return
    recalculate_invoice(instance.invoice)


@receiver(post_delete, sender=InvoiceLine)
def sync_invoice_totals_delete(sender, instance: InvoiceLine, **kwargs):
    if not _finance_signals_enabled():
        return
    recalculate_invoice(instance.invoice)


@receiver(post_save, sender=Payment)
def sync_payment(sender, instance: Payment, created: bool, **kwargs):
    if not _finance_signals_enabled():
        return
    if not instance.receipt_number:
        receipt = f"RCPT-{instance.id:05d}"
        school_id = getattr(instance, "school_id", None)
        if school_id is None and getattr(instance, "invoice_id", None):
            # tenant-isolation-allow: signal-handler-scoped-via-instance-school-fk
            school_id = getattr(getattr(instance, "invoice", None), "school_id", None)
        queryset = Payment.objects.filter(id=instance.id, receipt_number="")
        if school_id is not None:
            queryset = queryset.filter(school_id=school_id)
        updated = _run_with_optional_school_rls(
            school_id,
            lambda: queryset.update(receipt_number=receipt),
            operation="sync_payment.receipt_number",
        )
        if updated:
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


@receiver(post_save, sender=Payment)
def attribute_processor_revenue_share(sender, instance: Payment, **kwargs):
    """Phase 1 platform revenue: record the referral revenue-share the platform accrues
    on GMV routed through this school's OWN gateway (BYO model — the money has already
    settled to the school; the processor owes the platform a rebate on routed volume).

    Best-effort by design: the accrual is a platform receivable, so a failure here must
    NEVER break the payment save. Fires only on meaningful settle/unsettle transitions;
    the upsert is idempotent, so repeated saves do not double-count.
    """
    if not _finance_signals_enabled():
        return
    if getattr(instance, "status", None) not in (
        "completed",
        "refunded",
        "failed",
        "cancelled",
    ):
        return
    try:
        from apps.billing.revenue_share import (
            record_processor_revenue_share_attribution,
        )

        record_processor_revenue_share_attribution(instance)
    except Exception:  # attribution is best-effort; the payment must still save
        logger.exception(
            "processor revenue-share attribution failed for payment %s",
            getattr(instance, "pk", None),
        )


@receiver(post_delete, sender=Payment)
def sync_payment_delete(sender, instance: Payment, **kwargs):
    if not _finance_signals_enabled():
        return
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
    school_id = getattr(student_profile, "school_id", None)
    if school_id is None and _requires_explicit_rls_context():
        from apps.schools.rls_context import rls_bypass

        # tenant-isolation-allow: signal-handler-scoped-via-instance-school-fk
        with rls_bypass():
            school_ids = list(
                # tenant-isolation-allow: signal-handler-scoped-via-instance-school-fk
                Invoice.objects.filter(student=student_profile)
                .exclude(school_id__isnull=True)
                .values_list("school_id", flat=True)
                .distinct()[:2]
            )
        if len(school_ids) == 1:
            school_id = school_ids[0]
        elif len(school_ids) > 1:
            raise ValueError(
                "_deactivate_reminders_for_student cannot choose between multiple invoice schools"
            )

    if school_id is None:
        logger.warning(
            "_deactivate_reminders_for_student skipped student_id=%s: missing school_id",
            getattr(student_profile, "pk", None),
        )
        return 0

    def _update():
        return PaymentReminder.objects.filter(
            invoice__student=student_profile,
            invoice__school_id=school_id,
            is_active=True,
        ).update(is_active=False)

    if _requires_explicit_rls_context():
        from apps.schools.rls_context import rls_school

        with rls_school(school_id):
            return _update()
    return _update()


def _on_student_inactive_stop_reminders(sender, instance, **kwargs):
    """When a student is marked inactive/withdrawn, stop their payment reminders."""
    if getattr(instance, "is_active", True) is False:
        _deactivate_reminders_for_student(instance)


try:
    from apps.people.models import StudentProfile

    post_save.connect(_on_student_inactive_stop_reminders, sender=StudentProfile)
except ImportError:
    pass
