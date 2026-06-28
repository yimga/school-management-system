"""
Server-owned payment.received notification intents (SFDP 1431).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _guardian_contacts_for_payment(payment) -> list[tuple[str, str]]:
    """Return (email, phone) pairs for linked guardians."""
    student = getattr(payment, "student", None)
    if student is None:
        return []
    contacts: list[tuple[str, str]] = []
    try:
        from apps.people.models import StudentGuardian

        # StudentGuardian links a guardian_user (FK) to a student and carries its
        # OWN email/phone columns. The prior `select_related("guardian", ...)` named
        # a field that does not exist on StudentGuardian (its relations are
        # guardian_user + student) — a FieldError that was silently swallowed by the
        # except below, so guardian payment-received contacts were NEVER resolved.
        # tenant-isolation-allow: student-guardian-fk-scoped-to-school-via-student
        links = StudentGuardian.objects.filter(student_id=student.pk).select_related(
            "guardian_user"
        )
        for link in links:
            user = getattr(link, "guardian_user", None)
            # Prefer the link's own contact columns; fall back to the user email.
            email = (
                getattr(link, "email", "")
                or (getattr(user, "email", "") if user else "")
                or ""
            ).strip()
            phone = (getattr(link, "phone", "") or "").strip()
            if email or phone:
                contacts.append((email, phone))
    except Exception:
        logger.debug("payment_received guardian lookup skipped", exc_info=True)
    return contacts


def dispatch_payment_received_intent(
    *,
    school,
    payment,
    locale: str = "en",
) -> dict[str, Any]:
    """
    Queue email + SMS for guardians — server-owned delivery only (never client SMTP).
    """
    import hashlib

    from apps.schoolops.email_delivery import send_transactional
    from apps.schoolops.notification_intent import render_notification_intent
    from apps.schoolops.sms_templates import render_payment_received_sms

    if school is None or payment is None:
        return {"dispatched": 0, "reason": "missing_context"}

    try:
        from apps.policies.resolvers import is_within_quiet_hours

        if is_within_quiet_hours(school):
            return {"dispatched": 0, "reason": "quiet_hours", "deferred": True}
    except Exception:
        logger.debug("quiet_hours check skipped for payment receipt", exc_info=True)

    amount = getattr(payment, "amount", None) or Decimal("0")
    currency = str(getattr(payment, "currency_code", None) or "USD")[:3]
    invoice = getattr(payment, "invoice", None)
    reference = ""
    if invoice is not None:
        reference = str(getattr(invoice, "reference", None) or invoice.pk)

    student = getattr(payment, "student", None)
    student_name = str(
        getattr(student, "full_name", None) or getattr(student, "name", "") or "your student"
    )

    context = {
        "amount": str(amount),
        "currency": currency,
        "reference": reference,
        "student_name": student_name,
    }
    subject, body, html_body = render_notification_intent(
        template_key="payment_received",
        locale=locale,
        context=context,
    )
    tenant_hash = hashlib.sha256(str(school.pk).encode()).hexdigest()[:12]
    emails_sent = 0
    sms_sent = 0

    for email, phone in _guardian_contacts_for_payment(payment)[:20]:
        if email and "@" in email:
            try:
                send_transactional(
                    subject=subject,
                    body=body,
                    to=email,
                    html_body=html_body,
                    async_send=True,
                    tenant_hash=tenant_hash,
                    school=school,
                    idempotency_key=f"payment-received:{payment.pk}:{hashlib.sha256(email.encode()).hexdigest()[:12]}",
                )
                emails_sent += 1
            except Exception:
                logger.warning(
                    "payment_received email failed school_id=%s payment_id=%s",
                    getattr(school, "pk", None),
                    getattr(payment, "pk", None),
                    exc_info=True,
                )
        if phone:
            try:
                from importlib import import_module

                sms_body = render_payment_received_sms(locale=locale, context=context)
                for mod_path in (
                    "apps.notifications.sms_helpers",
                    "apps.communication.sms_helpers",
                ):
                    try:
                        mod = import_module(mod_path)
                    except ImportError:
                        continue
                    send_sms = getattr(mod, "send_sms", None)
                    if callable(send_sms):
                        send_sms(phone, sms_body)
                        sms_sent += 1
                        break
            except Exception:
                logger.debug("payment_received sms skipped", exc_info=True)

    return {
        "dispatched": emails_sent + sms_sent,
        "emails": emails_sent,
        "sms": sms_sent,
    }
