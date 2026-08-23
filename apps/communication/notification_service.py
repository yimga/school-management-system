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
from django.db import DatabaseError

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
            from apps.siteconfig.config_service import get_effective_site_settings

            # config-resolver-allow: namespace object is returned to callers (explicit site_settings override contract)
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
    # Route through the reliability layer (audit H4/observability) so tenant
    # notifications are retried + audited to EmailDeliveryEvent like every
    # other send, instead of a second unaudited facade. Falls back to Django's
    # send_mail only if the reliability layer is unimportable.
    try:
        from apps.schoolops.email_delivery import send_transactional

        recipients = list(to_addresses)
        result = send_transactional(
            subject=subject,
            body=body,
            to=recipients,
            html_body=html_message,
            from_email=from_addr,
            priority="transactional",
            school=school,
        )
        ok = bool(result.get("ok") or result.get("queued"))
        if ok:
            logger.info(
                "notification_service.email_sent count=%d subject=%s",
                len(recipients), (subject or "")[:50],
            )
        if not ok and not fail_silently:
            raise RuntimeError(result.get("error_kind") or "email_send_failed")
        return ok
    except _NOTIFICATION_EMAIL_SEND_ERRORS as e:
        logger.exception("Email send failed: %s", type(e).__name__)
        if not fail_silently:
            raise
        return False
    except ImportError:
        try:
            django_send_mail(
                subject=subject,
                message=body,
                from_email=from_addr,
                recipient_list=list(to_addresses),
                html_message=html_message,
                fail_silently=fail_silently,
            )
            return True
        except _NOTIFICATION_EMAIL_SEND_ERRORS as e:
            logger.exception("Email send failed: %s", type(e).__name__)
            if not fail_silently:
                raise
            return False


def _enqueue_outbound(
    *,
    channel: str,
    recipient: str,
    body: str,
    school: Any = None,
    idempotency_key: Optional[str] = None,
) -> bool:
    """Durably queue a failed SMS/WhatsApp send for later retry (audit residual).

    Previously a provider failure was lost unless the caller manually wrote an
    ``OutboundMessageQueue`` row — almost no caller did, so a transient provider
    outage silently dropped the message. We now auto-enqueue on failure; the
    ``process_outbound_message_queue`` Celery beat drains the row when the
    provider recovers (atomic claim + 3 retries + stale recovery).

    Opt-out via ``RMC_AUTO_ENQUEUE_OUTBOUND=0``. Idempotent when an
    ``idempotency_key`` is supplied (won't double-queue an in-flight row).
    Best-effort — never raises into the send path.
    """
    if not (recipient and body):
        return False
    if not getattr(settings, "RMC_AUTO_ENQUEUE_OUTBOUND", True):
        return False
    try:
        from apps.communication.models import OutboundMessageQueue

        key = (idempotency_key or "").strip()[:255]
        if key:
            # Don't re-queue a row that's already pending/retrying for this key.
            # tenant-isolation-allow: outbound queue keyed by idempotency_key; drainer is school-scoped
            exists = OutboundMessageQueue.objects.filter(
                idempotency_key=key, status__in=("pending", "retrying"),
            ).exists()
            if exists:
                return True
        OutboundMessageQueue.objects.create(
            school=school if (school is not None and getattr(school, "pk", None)) else None,
            channel=channel,
            recipient_identifier=str(recipient)[:255],
            body=body,
            status="pending",
            idempotency_key=key,
        )
        logger.info(
            "notification_service.outbound_enqueued channel=%s (provider failed, queued for retry)",
            channel,
        )
        return True
    except Exception as exc:  # broad-by-design — enqueue never breaks the caller
        logger.warning(
            "notification_service.outbound_enqueue_failed channel=%s err=%s",
            channel, type(exc).__name__,
        )
        return False


def _bump_sms_usage_meter(school: Any, body: str) -> None:
    """Roll SMS into billing UsageMeter (segments — coarse GSM-7 estimate).

    v4.00.36: also emit the canonical billing-layer ``sms_count`` dimension
    (one tick per message) so dashboards / budget gates can read a
    message-count without inferring it from segments.
    """
    if school is None:
        return
    try:
        from apps.marketplace.monetization import USAGE_METRIC_SMS, record_usage_meter_increment

        text = body or ""
        segments = max(1, (len(text) + 159) // 160)  # magic-number-allow: sms-segment-length
        record_usage_meter_increment(
            school=school,
            metric_code=USAGE_METRIC_SMS,
            quantity=segments,
            metadata={"source": "notification_service.send_sms"},
        )
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("SMS usage meter rollup skipped", exc_info=True)
    try:
        from apps.billing.models_metering import record as _record_dim

        _record_dim(school, "sms_count", delta=1)
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("SMS sms_count dimension rollup skipped", exc_info=True)


def _record_sms_route_attempts(outcome: Any, *, recipient: str, school: Any = None) -> None:
    """Persist every multi-gateway provider attempt to MessageDeliveryReceipt.

    Maps the router's ``SMSRouteAttempt`` trail onto the existing delivery-receipt
    table (PII-hashed recipient, tenant-scoped, terminal-flag) via the canonical
    ``record_delivery_receipt`` helper:

    * a successful attempt is keyed by the provider's real message id and stored
      as ``accepted`` — so the later provider status-callback webhook upserts the
      SAME row (``accepted`` → ``sent`` → ``delivered``);
    * a failed attempt has no provider message id, so we synthesize a collision-
      free key (``failover:<provider>:<hash>:<uuid>``) and store ``failed`` with
      the provider error mapped onto ``error_code``.

    Best-effort — receipt persistence NEVER breaks the send path.
    """
    attempts = getattr(outcome, "attempts", None) or []
    if not attempts:
        return
    try:
        import uuid as _uuid

        from apps.communication.delivery_receipts import (
            _hash_recipient,
            record_delivery_receipt,
        )

        for attempt in attempts:
            result = attempt.result
            provider_key = attempt.provider_key
            if result.ok and result.provider_message_id:
                record_delivery_receipt(
                    channel="sms",
                    provider=provider_key,
                    provider_message_id=result.provider_message_id,
                    recipient=recipient,
                    status="accepted",
                    school=school,
                )
            else:
                synthetic_id = (
                    f"failover:{provider_key}:"
                    f"{_hash_recipient(recipient)}:{_uuid.uuid4().hex[:12]}"
                )
                record_delivery_receipt(
                    channel="sms",
                    provider=provider_key,
                    provider_message_id=synthetic_id,
                    recipient=recipient,
                    status="failed",
                    error_code=(result.error or "")[:32],
                    school=school,
                )
    except Exception as exc:  # broad-by-design — receipts never break the send
        logger.warning(
            "notification_service.sms_route_receipt_failed err=%s",
            type(exc).__name__,
        )


def _sms_idempotency_reserve(*, key: str, to_phone: str, school: Any) -> Any:
    """GAP-7 provider-level idempotency reservation.

    Gate the *provider* send (not just the enqueue layer) on the persisted
    ``SmsSendLog`` ledger so an SMS retry that reaches the provider twice never
    double-sends a real message. Returns one of:

    * ``"duplicate"`` — a SENT row already exists for this key, OR a concurrent
      writer already holds a PENDING row (we lost the ``get_or_create`` race and
      another in-flight send owns the dispatch); the caller MUST NOT call the
      provider. A FAILED row is NOT a duplicate — it is reclaimed below.
    * an ``SmsSendLog`` instance (status PENDING) — this call owns the dispatch
      and must finalize the row via :func:`_sms_idempotency_finalize`.
    * ``None`` — fail-open: the ledger is unavailable (DB hiccup) so we proceed
      with the send rather than block every SMS on an idempotency-ledger outage.

    Recipient is stored hashed only (sha256 hex prefix via the canonical
    ``delivery_receipts._hash_recipient`` — never the raw phone).
    """
    try:
        from apps.communication.delivery_receipts import _hash_recipient
        from apps.communication.models import SmsSendLog

        # Already dispatched for this logical send → duplicate, do not re-send.
        # tenant-isolation-allow: sms-send-log keyed by unique idempotency_key
        already_sent = SmsSendLog.objects.filter(
            idempotency_key=key, status=SmsSendLog.Status.SENT,
        ).exists()
        if already_sent:
            return "duplicate"

        log_row, created = SmsSendLog.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "recipient_hash": _hash_recipient(to_phone),
                "school": school if (school is not None and getattr(school, "pk", None)) else None,
                "status": SmsSendLog.Status.PENDING,
            },
        )
        if not created:
            # A FAILED row is a spent attempt, not an in-flight one: the provider
            # rejected it and the queue row went to "retrying". Reclaiming it
            # (conditionally, so a concurrent reclaim loses the race) lets the
            # retry actually reach the provider. Without this the retry was
            # reported "duplicate" -> send_sms returned True -> the drainer
            # marked the queue row sent for a message nobody ever received.
            reclaimed = SmsSendLog.objects.filter(
                pk=log_row.pk, status=SmsSendLog.Status.FAILED
            ).update(status=SmsSendLog.Status.PENDING)
            if reclaimed:
                log_row.status = SmsSendLog.Status.PENDING
                return log_row
            # A concurrent PENDING/SENT row already owns this key — treat as a
            # duplicate so only the first writer dispatches to the provider.
            return "duplicate"
        return log_row
    except Exception as exc:  # broad-by-design — ledger outage must not block SMS
        logger.warning(
            "notification_service.sms_idempotency_reserve_failed err=%s (failing open)",
            type(exc).__name__,
        )
        return None


def _sms_idempotency_finalize(log_row: Any, *, sent: bool, outcome: Any = None) -> None:
    """Mark a reserved ``SmsSendLog`` row SENT (+provider_message_id) or FAILED.

    Best-effort — a ledger write error here never breaks the send path (the
    message was already dispatched by the time we finalize). No raw PII is read
    or logged.
    """
    if log_row is None:
        return
    try:
        from apps.communication.models import SmsSendLog

        if sent:
            log_row.status = SmsSendLog.Status.SENT
            provider_key = getattr(outcome, "provider_key", None)
            if provider_key:
                log_row.provider = str(provider_key)[:32]
            result = getattr(outcome, "result", None)
            provider_message_id = getattr(result, "provider_message_id", None)
            if provider_message_id:
                log_row.provider_message_id = str(provider_message_id)[:128]
            log_row.save(
                update_fields=["status", "provider", "provider_message_id"],
            )
        else:
            log_row.status = SmsSendLog.Status.FAILED
            log_row.save(update_fields=["status"])
    except Exception as exc:  # broad-by-design — finalize never breaks the send
        logger.warning(
            "notification_service.sms_idempotency_finalize_failed err=%s",
            type(exc).__name__,
        )


def send_sms(
    to_phone: str,
    body: str,
    *,
    school: Any = None,
    site_settings: Any = None,
    fallback_email: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    queue_on_failure: bool = True,
) -> bool:
    """
    Send SMS via configured provider adapter (Twilio, AfricasTalking).
    If no provider or SMS fails and fallback_email is provided, send email instead.
    to_phone: E.164-style (leading + optional).
    """
    to_phone = (to_phone or "").strip().replace(" ", "")
    if to_phone and not to_phone.startswith("+"):
        to_phone = "+" + to_phone
    # Honour SMS opt-out (audit residual). A recipient who texted STOP has a
    # trailing ``withdrawn`` consent event — we must not message them. Best-
    # effort: a consent-log read error fails open (see consent.is_channel_suppressed).
    try:
        from apps.communication.consent import is_channel_suppressed

        if to_phone and is_channel_suppressed("sms", to_phone):
            logger.info("send_sms skipped: recipient opted out of SMS")
            return False
    except ImportError:
        pass
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
            return True
        # No fallback substituted the SMS — queue it so it isn't lost while the
        # circuit is open (audit residual: silent loss on provider outage).
        if queue_on_failure:
            _enqueue_outbound(
                channel="sms", recipient=to_phone, body=body, school=school,
                idempotency_key=idempotency_key,
            )
        return False
    provider = get_sms_provider(site)
    if provider:
        # GAP-1 failover: route through the country-aware multi-gateway router so
        # a primary-provider outage fails over to the next configured provider
        # (e.g. Twilio → AfricasTalking) BEFORE the circuit breaker / fallback /
        # enqueue path engages. With a single configured provider the chain has
        # one live link, so behaviour is identical to the old direct send. The
        # circuit-breaker open-check above already gated us in; we record
        # success/failure per the *overall* routing outcome below.
        from apps.communication.sms_router import SMSMultiGatewayRouter

        # GAP-7: provider-level idempotency. The enqueue layer only de-dupes at
        # the OutboundMessageQueue; a retry that reaches the provider twice could
        # still double-send a real SMS. When a non-empty idempotency_key is
        # supplied we gate the actual provider call on the persisted SmsSendLog
        # ledger: a prior SENT row (or a concurrent in-flight row) short-circuits
        # the send. With no key the behaviour is unchanged (best-effort, no row).
        idem_key = (idempotency_key or "").strip()[:128]
        sms_log_row = None
        if idem_key:
            reservation = _sms_idempotency_reserve(
                key=idem_key, to_phone=to_phone, school=school,
            )
            if reservation == "duplicate":
                logger.info(
                    "send_sms deduped: provider send already recorded for idempotency_key (no double-send)",
                )
                return True  # already sent — truthy, provider NOT called again
            sms_log_row = reservation  # PENDING row we own, or None (fail-open)

        router = SMSMultiGatewayRouter.for_destination(site, to_phone)
        outcome = router.route(to_phone, body, idempotency_key=idempotency_key)
        _record_sms_route_attempts(
            outcome, recipient=to_phone, school=school,
        )
        if outcome.ok:
            _sms_idempotency_finalize(sms_log_row, sent=True, outcome=outcome)
            circuit_record_success(school_id, "sms")
            _bump_sms_usage_meter(school, body)
            return True
        # Every provider in the chain failed — now (and only now) trip the
        # breaker and fall through to the existing fallback / enqueue path.
        _sms_idempotency_finalize(sms_log_row, sent=False, outcome=outcome)
        circuit_record_failure(school_id, "sms")
        if fallback_email and body:
            send_email(
                [fallback_email],
                subject="Message from school",
                body=body,
                site_settings=site,
            )
            return True
        # Provider failed and nothing substituted — durably queue for retry.
        if queue_on_failure:
            _enqueue_outbound(
                channel="sms", recipient=to_phone, body=body, school=school,
                idempotency_key=idempotency_key,
            )
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
    _bump_sms_usage_meter(school, body)
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
    idempotency_key: Optional[str] = None,
    queue_on_failure: bool = True,
) -> bool:
    """Delegate to channels.send_whatsapp (tenant-configured WhatsApp Business API).

    On provider failure, a plain-body message is durably queued to
    ``OutboundMessageQueue`` for retry by the drainer (audit residual: silent
    loss on provider outage). Template messages are not auto-queued because the
    queue replays a raw text body, not a template envelope.
    """
    from .channels import send_whatsapp as _send_whatsapp

    ok = _send_whatsapp(
        school,
        to_phone,
        template_name=template_name,
        template_params=template_params,
        body=body,
    )
    if not ok and queue_on_failure and body and not template_name:
        _enqueue_outbound(
            channel="whatsapp", recipient=to_phone, body=body, school=school,
            idempotency_key=idempotency_key,
        )
    return ok


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
