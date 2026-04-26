"""
Unified notification service (internal-first). Single entry point for email, SMS, push, WhatsApp.
All callers use this; no app imports Twilio/send_mail/EmailMessage directly for notifications.
SMS fallback: if SMS fails or is not configured, optional fallback to email.
§2.4: broad except replaced with typed exception tuples.
"""

from __future__ import annotations

import logging
from smtplib import SMTPException
from typing import Any, List, Optional

from django.conf import settings
from django.core.mail import send_mail as django_send_mail

from .circuit_breaker import (
    is_open as circuit_is_open,
    record_failure as circuit_record_failure,
    record_success as circuit_record_success,
)
from .providers import get_sms_provider

logger = logging.getLogger(__name__)

# §2.4: typed exceptions for settings resolution and email send
_NOTIFICATION_SETTINGS_RESOLVE_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)
_NOTIFICATION_EMAIL_SEND_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    SMTPException,
)


def _resolve_site_settings(school: Any = None, site_settings: Any = None):
    """Resolve effective tenant site settings (slim row via get_effective_site_settings) from school or explicit override."""
    if site_settings is not None:
        return site_settings
    if school is not None:
        try:
            from apps.platform_runtime.site_settings_read_access import get_effective_site_settings

            return get_effective_site_settings(school=school)
        except _NOTIFICATION_SETTINGS_RESOLVE_ERRORS:
            logger.debug(
                "resolve_site_settings skip for school id=%s",
                getattr(school, "id", None),
                exc_info=True,
            )
    return getattr(settings, "SITE_SETTINGS", None)


def send_email(
    to_addresses: List[str],
    subject: str,
    body: str,
    *,
    html_message: Optional[str] = None,
    from_email: Optional[str] = None,
    school: Any = None,
    site_settings: Any = None,
    fail_silently: bool = True,
) -> bool:
    """
    Send email via Django backend. Single internal contract.
    to_addresses: list of email strings.
    """
    if not to_addresses:
        return False
    site = _resolve_site_settings(school=school, site_settings=site_settings)
    from_addr = (
        from_email
        or (getattr(site, "email_from_address", None) if site else None)
        or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@runmycampus.com")
    )
    try:
        django_send_mail(
            subject=subject,
            message=body,
            from_email=from_addr,
            recipient_list=list(to_addresses),
            html_message=html_message,
            fail_silently=fail_silently,
        )
        logger.info("Email sent to %s: %s", to_addresses, subject[:50])
        return True
    except _NOTIFICATION_EMAIL_SEND_ERRORS as e:
        logger.exception("Email send failed: %s", e)
        if not fail_silently:
            raise
        return False


def send_sms(
    to_phone: str,
    body: str,
    *,
    school: Any = None,
    site_settings: Any = None,
    fallback_email: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> bool:
    """
    Send SMS via configured provider adapter (Twilio, AfricasTalking).
    If no provider or SMS fails and fallback_email is provided, send email instead.
    to_phone: E.164-style (leading + optional).
    """
    to_phone = (to_phone or "").strip().replace(" ", "")
    if to_phone and not to_phone.startswith("+"):
        to_phone = "+" + to_phone
    site = _resolve_site_settings(school=school, site_settings=site_settings)
    school_id = getattr(school, "id", None) if school else None
    if circuit_is_open(school_id, "sms"):
        logger.warning(
            "Circuit open for SMS (school_id=%s); skipping provider", school_id
        )
        if fallback_email and body:
            send_email(
                [fallback_email],
                subject="Message from school",
                body=body,
                site_settings=site,
            )
        return bool(fallback_email)
    provider = get_sms_provider(site)
    if provider:
        result = provider.send(to_phone, body, idempotency_key=idempotency_key)
        if result.ok:
            circuit_record_success(school_id, "sms")
            return True
        circuit_record_failure(school_id, "sms")
        if fallback_email and body:
            send_email(
                [fallback_email],
                subject="Message from school",
                body=body,
                site_settings=site,
            )
            return True
        return False
    # No SMS provider (e.g. console): log and optionally fallback to email
    logger.info("[CONSOLE SMS] %s: %s", to_phone, body[:100])
    if fallback_email and body:
        send_email(
            [fallback_email],
            subject="Message from school",
            body=body,
            site_settings=site,
        )
        return True
    return True  # console mode counts as "sent" for dev


def send_push(
    school: Any,
    token_or_user: Any,
    title: str,
    body: str,
    *,
    data: Optional[dict] = None,
) -> bool:
    """Delegate to channels.send_push (tenant-configured FCM/APNS)."""
    from .channels import send_push as _send_push

    return _send_push(school, token_or_user, title, body, data=data)


def send_whatsapp(
    school: Any,
    to_phone: str,
    *,
    template_name: Optional[str] = None,
    template_params: Optional[List[str]] = None,
    body: Optional[str] = None,
) -> bool:
    """Delegate to channels.send_whatsapp (tenant-configured WhatsApp Business API)."""
    from .channels import send_whatsapp as _send_whatsapp

    return _send_whatsapp(
        school,
        to_phone,
        template_name=template_name,
        template_params=template_params,
        body=body,
    )


def get_notification_service():
    """Return the unified notification service facade (for code that expects a class)."""
    return UnifiedNotificationService()


class UnifiedNotificationService:
    """
    Facade for backward compatibility: evals/notifications and others can use
    service.send_email(...), service.send_sms(...) with same semantics.
    """

    def __init__(self, school: Any = None, site_settings: Any = None):
        self._school = school
        self._site = site_settings or _resolve_site_settings(school=school)

    def send_email(
        self, to_addresses, subject, body, *, html_message=None, from_email=None
    ):
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]
        return send_email(
            to_addresses,
            subject,
            body,
            html_message=html_message,
            from_email=from_email,
            school=self._school,
            site_settings=self._site,
        )

    def send_sms(
        self, phone_number: str, message: str, *, fallback_email: Optional[str] = None
    ) -> bool:
        return send_sms(
            phone_number,
            message,
            school=self._school,
            site_settings=self._site,
            fallback_email=fallback_email,
        )

    def send_push(self, token_or_user, title: str, body: str, *, data=None) -> bool:
        if self._school is None:
            logger.warning("send_push requires school")
            return False
        return send_push(self._school, token_or_user, title, body, data=data)

    def send_whatsapp(
        self, to_phone: str, *, template_name=None, template_params=None, body=None
    ) -> bool:
        if self._school is None:
            logger.warning("send_whatsapp requires school")
            return False
        return send_whatsapp(
            self._school,
            to_phone,
            template_name=template_name,
            template_params=template_params,
            body=body,
        )
