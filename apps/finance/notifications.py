"""
Finance in-app and optional email notifications to guardians.
Phase 2: New invoice issued (2.3), Payment received (2.4).
Configurable via SiteSettings; respects guardians with can_view_finance.
"""
from __future__ import annotations

import contextvars
import logging
from django.urls import reverse

# When True, skip automatic new-invoice notification (e.g. during bulk create; use "Notify guardians" instead).
_skip_new_invoice_notify: contextvars.ContextVar[bool] = contextvars.ContextVar("skip_new_invoice_notify", default=False)

from apps.finance.models import Invoice, Payment, Notification
from apps.people.models import StudentGuardian
from apps.siteconfig.models import SiteSettings

logger = logging.getLogger(__name__)


def _guardians_with_finance_access(invoice: Invoice):
    """Guardians who can view finance for this invoice's student."""
    if not invoice.student_id:
        return []
    return list(
        StudentGuardian.objects.filter(
            student=invoice.student,
            can_view_finance=True,
            guardian_user__isnull=False,
            guardian_user__is_active=True,
        ).select_related("guardian_user")
    )


def _invoice_link(invoice: Invoice) -> str:
    try:
        return reverse("finance:invoice_detail", args=[invoice.id])
    except Exception:
        return f"/finance/invoices/{invoice.id}/"


def notify_guardians_new_invoice(
    invoice: Invoice,
    *,
    created_by=None,
    send_email: bool | None = None,
    force: bool = False,
) -> int:
    """
    Send in-app notification (and optionally email) to guardians with finance access
    when a new invoice is issued. Returns number of notifications created.
    When force=False, skips if _skip_new_invoice_notify is set (bulk create).
    """
    if not force and _skip_new_invoice_notify.get():
        return 0
    site = SiteSettings.get_solo()
    if not getattr(site, "finance_notify_guardians_new_invoice", True):
        return 0
    guardians = _guardians_with_finance_access(invoice)
    if not guardians:
        return 0
    ref = invoice.reference or f"INV-{invoice.id}"
    amount = getattr(invoice, "total_amount", None)
    if amount is None:
        amount = getattr(invoice, "balance_amount", None)
    amount_str = f" ({amount})" if amount is not None else ""
    title = "New invoice issued"
    message = f"Invoice {ref}{amount_str} has been issued for {invoice.student}. View and pay in the portal."
    link = _invoice_link(invoice)
    count = 0
    for g in guardians:
        user = g.guardian_user
        if not user:
            continue
        Notification.objects.create(
            title=title,
            message=message,
            link=link,
            severity=Notification.Severity.INFO,
            recipient=user,
            created_by=created_by,
        )
        count += 1
    if send_email is None:
        send_email = getattr(site, "finance_notify_new_invoice_email", False)
    if send_email and count:
        _send_new_invoice_emails(invoice, guardians)
    return count


def _send_new_invoice_emails(invoice: Invoice, guardians: list) -> None:
    """Send optional email to guardians (Phase 2.3)."""
    from django.core.mail import EmailMessage
    from django.conf import settings
    ref = invoice.reference or f"INV-{invoice.id}"
    subject = f"New invoice: {ref}"
    body = (
        f"Invoice {ref} has been issued for {invoice.student}. "
        "Log in to the parent portal to view details and pay."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@school.example")
    for g in guardians:
        email = (getattr(g, "email", None) or "").strip() or (g.guardian_user.email or "").strip()
        if email:
            try:
                EmailMessage(subject, body, from_email, [email]).send(fail_silently=True)
            except Exception as e:
                logger.warning("Failed to send new-invoice email to %s: %s", email, e)


def notify_guardians_payment_received(
    payment: Payment,
    *,
    created_by=None,
    send_email: bool | None = None,
) -> int:
    """
    Send in-app notification (and optionally email) to guardians when a payment is recorded.
    Phase 2.4. Returns number of notifications created.
    """
    site = SiteSettings.get_solo()
    if not getattr(site, "finance_notify_guardians_payment_received", True):
        return 0
    invoice = payment.invoice
    if not invoice:
        return 0
    guardians = _guardians_with_finance_access(invoice)
    if not guardians:
        return 0
    ref = invoice.reference or f"INV-{invoice.id}"
    title = "Payment received"
    message = f"Payment of {payment.amount} for invoice {ref} has been recorded."
    link = _invoice_link(invoice)
    count = 0
    for g in guardians:
        user = g.guardian_user
        if not user:
            continue
        Notification.objects.create(
            title=title,
            message=message,
            link=link,
            severity=Notification.Severity.INFO,
            recipient=user,
            created_by=created_by,
        )
        count += 1
    if send_email is None:
        send_email = getattr(site, "finance_notify_payment_received_email", False)
    if send_email and count:
        _send_payment_received_emails(payment, guardians)
    return count


def _send_payment_received_emails(payment: Payment, guardians: list) -> None:
    """Optional email when payment is received (Phase 2.4)."""
    from django.core.mail import EmailMessage
    from django.conf import settings
    ref = payment.invoice.reference if payment.invoice else str(payment.id)
    subject = f"Payment received for invoice {ref}"
    body = f"Payment of {payment.amount} has been recorded for invoice {ref}."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@school.example")
    for g in guardians:
        email = (getattr(g, "email", None) or "").strip() or (g.guardian_user.email or "").strip()
        if email:
            try:
                EmailMessage(subject, body, from_email, [email]).send(fail_silently=True)
            except Exception as e:
                logger.warning("Failed to send payment-received email to %s: %s", email, e)


def notify_guardians_new_invoices_bulk(
    invoice_ids: list[int],
    *,
    created_by=None,
    send_email: bool | None = None,
) -> int:
    """
    Notify guardians for multiple invoices (e.g. after bulk generate).
    Phase 4.1: Post–bulk "Notify guardians" action.
    Uses force=True so notifications are sent even when site would skip auto-notify.
    Returns total number of in-app notifications created.
    """
    from apps.finance.models import Invoice
    total = 0
    for inv in Invoice.objects.filter(id__in=invoice_ids).select_related("student"):
        total += notify_guardians_new_invoice(
            inv, created_by=created_by, send_email=send_email, force=True
        )
    return total
