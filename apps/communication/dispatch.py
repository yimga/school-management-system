"""Event → preference → channel notification router (GAP-3 / MED-4).

Single place that answers: "an ``event_key`` happened for ``recipient`` — which
channels should it fan out to, and is each one *permitted* right now?".

Before Phase 4 every caller hardcoded its channel ("send an SMS for a fee
reminder") and the granular :class:`~apps.communication.models.NotificationPreference`
(reinstated in Phase 2) was consulted *nowhere*. This module wires the two
together:

    event_key ──EVENT_CATEGORY_MAP──▶ Category
    Category  ──DEFAULT_CHANNELS_BY_CATEGORY──▶ [Channel, ...]
    pref.is_muted(category)  → skip the whole event
    pref.allows(category, channel)  → skip that one channel
    per-channel transport gate (consent / guardian flags / quiet hours)

Design rules honoured here:

* **No hardcoded channel strings scattered around** — the two maps below are the
  single source of truth, keyed off the model's ``TextChoices`` (never bare
  literals at a transport call site).
* **Tenant isolation** — ``school`` is threaded through every transport and the
  in-app :class:`finance.Notification` row carries it.
* **PII-safe** — phone/email are resolved locally and never logged; SMS consent
  uses the hashing helper in :mod:`apps.communication.consent`.
* **Honest reporting** — a muted / deferred / failed channel is reported as
  exactly that in the result dict, never silently as "sent".
* **Failure-isolated** — every transport runs inside its own ``try/except`` so
  one channel raising can never abort the others.
* **No app-load cycles** — transports + models are imported lazily *inside*
  :func:`dispatch_event`.

Callers are migrated to use :func:`dispatch_event` in Phase 4; this module does
not edit or wrap any existing call site.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.communication.models import NotificationPreference

logger = logging.getLogger(__name__)

# Local aliases so the rest of the module references the model's TextChoices
# rather than bare string literals (no-hardcoding rule).
Category = NotificationPreference.Category
Channel = NotificationPreference.Channel


# ---------------------------------------------------------------------------
# Routing tables — the single source of truth for event → category → channels.
# Defined ONCE; every resolution reads these (no scattered literals).
# ---------------------------------------------------------------------------

#: Maps a dotted ``event_key`` to the preference Category that governs it.
#: Unknown keys fall back to :data:`DEFAULT_CATEGORY` via :func:`category_for_event`.
EVENT_CATEGORY_MAP: Dict[str, str] = {
    # Fees / billing / meals
    "invoice.created": Category.FEES,
    "payment.received": Category.FEES,
    "fee.reminder": Category.FEES,
    "meal.low_balance": Category.FEES,
    # Academics
    "grade.published": Category.GRADES,
    "attendance.absent": Category.ATTENDANCE,
    # Broadcast / messaging
    "announcement.published": Category.ANNOUNCEMENTS,
    "message.received": Category.MESSAGES,
    # Behaviour / admissions
    "discipline.incident": Category.DISCIPLINE,
    "applicant.admitted": Category.ADMISSIONS,
}

#: Category used for any event_key not present in :data:`EVENT_CATEGORY_MAP`.
DEFAULT_CATEGORY: str = Category.SYSTEM

#: Which channels each Category fans to by default (overridable per call via the
#: ``channels=`` arg, and further narrowed per-user by ``pref.allows(...)``).
DEFAULT_CHANNELS_BY_CATEGORY: Dict[str, List[str]] = {
    Category.FEES: [Channel.EMAIL, Channel.IN_APP, Channel.SMS],
    Category.GRADES: [Channel.EMAIL, Channel.IN_APP],
    Category.ATTENDANCE: [Channel.EMAIL, Channel.IN_APP, Channel.SMS],
    Category.ANNOUNCEMENTS: [Channel.EMAIL, Channel.IN_APP, Channel.PUSH],
    Category.MESSAGES: [Channel.IN_APP, Channel.PUSH],
    Category.DISCIPLINE: [Channel.EMAIL, Channel.IN_APP, Channel.SMS],
    Category.ADMISSIONS: [Channel.EMAIL, Channel.IN_APP],
    Category.SYSTEM: [Channel.IN_APP],
}

#: Transports that wrap their own failure handling never re-raise into the
#: router, but a programming/runtime error in our gate logic must still be
#: isolated per-channel — these are the types we catch + report (we keep this
#: broad because a single bad channel must never sink the others; see
#: per-channel ``try/except`` in :func:`dispatch_event`).
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (Exception,)


def category_for_event(event_key: str) -> str:
    """Resolve an ``event_key`` to its :class:`NotificationPreference.Category`.

    Unknown keys map to :data:`DEFAULT_CATEGORY` (SYSTEM) — a new event is still
    deliverable (default channels) rather than silently dropped.
    """
    return EVENT_CATEGORY_MAP.get((event_key or "").strip(), DEFAULT_CATEGORY)


def get_preference(user: Any) -> Optional[NotificationPreference]:
    """Best-effort load of a user's :class:`NotificationPreference`.

    Returns ``None`` (treated downstream as "no preference set → defaults apply")
    when the user is missing, has no preference row, or the lookup errors. Never
    raises — a preference-table blip must not block a notification.
    """
    if user is None or not getattr(user, "pk", None):
        return None
    # Use the OneToOne reverse accessor when it's already cached; otherwise query.
    try:
        pref = getattr(user, "notification_preference", None)
        if isinstance(pref, NotificationPreference):
            return pref
    except NotificationPreference.DoesNotExist:
        return None
    except Exception:  # broad-by-design — reverse accessor never breaks the send
        logger.debug("get_preference reverse-accessor failed", exc_info=True)
    try:
        return NotificationPreference.objects.filter(user=user).first()
    except Exception:  # broad-by-design — pref lookup never breaks the send
        logger.debug("get_preference query failed", exc_info=True)
        return None


def _guardian_link_for(recipient: Any) -> Any:
    """Return a StudentGuardian link for this recipient, or ``None``.

    Coarse channel flags (``receives_email/receives_sms/receives_whatsapp``) live
    on :class:`people.StudentGuardian`. A recipient may guard several students;
    we read the first link (the flags are per-guardian-account, not per-student).
    Best-effort — never raises.
    """
    if recipient is None or not getattr(recipient, "pk", None):
        return None
    try:
        return getattr(recipient, "guardian_links", None) and recipient.guardian_links.first()
    except Exception:  # broad-by-design — guardian lookup never breaks the send
        logger.debug("guardian link lookup failed", exc_info=True)
        return None


def _now_local_time(pref: Optional[NotificationPreference]):
    """Current wall-clock ``time`` in the recipient's local timezone.

    Honours ``pref.timezone`` when set, else the active Django timezone. Returns
    a ``datetime.time`` suitable for :meth:`NotificationPreference.in_quiet_hours`.
    """
    now = timezone.now()
    tzname = getattr(pref, "timezone", "") if pref else ""
    if tzname:
        try:
            from zoneinfo import ZoneInfo

            return timezone.localtime(now, ZoneInfo(tzname)).time()
        except Exception:  # broad-by-design — bad tz name falls back to server tz
            logger.debug("quiet-hours tz resolve failed tz=%s", tzname, exc_info=True)
    return timezone.localtime(now).time()


def dispatch_event(
    event_key: str,
    *,
    recipient: Any,
    context: Dict[str, Any],
    school: Any = None,
    channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Route a single ``event_key`` to ``recipient`` across permitted channels.

    Parameters
    ----------
    event_key:
        Dotted event identifier (see :data:`EVENT_CATEGORY_MAP`).
    recipient:
        The target user (``settings.AUTH_USER_MODEL`` instance).
    context:
        Per-event payload. Recognised keys: ``title``, ``message``, ``link``,
        ``severity`` (in-app); ``email`` (email fallback address); ``phone``
        (SMS fallback number).
    school:
        Tenant scope — threaded through every transport and stamped on the in-app
        notification row.
    channels:
        Optional explicit channel list (values from
        :class:`NotificationPreference.Channel`). When omitted, the category's
        :data:`DEFAULT_CHANNELS_BY_CATEGORY` set is used. Either way each channel
        is still filtered by ``pref.allows(category, channel)``.

    Returns
    -------
    dict
        ``{"skipped": "muted", "category": <category>}`` if the whole category is
        muted; otherwise a results dict ``{"category": <category>, "results":
        {<channel>: <result>}}`` where each value honestly reports the outcome
        (``True``/``False`` for a transport, ``"skipped:pref"``,
        ``"deferred_quiet_hours"``, ``"suppressed"``, ``"no_address"``,
        ``"error:<Type>"``, etc.). A muted/deferred/failed channel is NEVER
        reported as sent.
    """
    context = context or {}
    category = category_for_event(event_key)
    pref = get_preference(recipient)

    # Whole-event mute short-circuit (honest skip).
    if pref is not None and pref.is_muted(category):
        return {"skipped": "muted", "category": category}

    target_channels = list(channels) if channels else list(
        DEFAULT_CHANNELS_BY_CATEGORY.get(category, DEFAULT_CHANNELS_BY_CATEGORY[DEFAULT_CATEGORY])
    )

    # Lazy imports — keep app-load free of transport/model import cycles.
    from apps.communication import notification_service
    from apps.communication.consent import is_channel_suppressed
    from apps.finance.models import Notification

    try:
        from apps.communication import web_push_service
    except ImportError:
        web_push_service = None

    guardian = _guardian_link_for(recipient)
    results: Dict[str, Any] = {}

    for channel in target_channels:
        # Per-user channel permission (override list / category gate).
        if pref is not None and not pref.allows(category, channel):
            results[channel] = "skipped:pref"
            continue

        # Each transport is failure-isolated: one channel raising never aborts
        # the rest (PII-safe — we log the error *type* only, never the payload).
        try:
            if channel == Channel.IN_APP:
                results[channel] = _send_in_app(
                    Notification, recipient=recipient, context=context, school=school,
                )

            elif channel == Channel.EMAIL:
                results[channel] = _send_email(
                    notification_service,
                    recipient=recipient,
                    context=context,
                    school=school,
                    guardian=guardian,
                )

            elif channel == Channel.SMS:
                results[channel] = _send_sms(
                    notification_service,
                    is_channel_suppressed,
                    recipient=recipient,
                    context=context,
                    school=school,
                    guardian=guardian,
                    pref=pref,
                )

            elif channel == Channel.PUSH:
                results[channel] = _send_push(
                    notification_service,
                    web_push_service,
                    recipient=recipient,
                    context=context,
                    school=school,
                )

            else:
                # Unknown / not-yet-wired channel (e.g. WHATSAPP) — honest report.
                results[channel] = "unsupported_channel"

        except _TRANSPORT_ERRORS as exc:
            logger.warning(
                "dispatch_event channel failed event=%s channel=%s err=%s",
                event_key, channel, type(exc).__name__,
            )
            results[channel] = f"error:{type(exc).__name__}"

    return {"category": category, "results": results}


# ---------------------------------------------------------------------------
# Per-channel transports. Each returns a JSON-friendly outcome and is called
# inside the failure-isolating try/except above.
# ---------------------------------------------------------------------------


def _send_in_app(Notification, *, recipient: Any, context: Dict[str, Any], school: Any):
    """Create the in-app :class:`finance.Notification` row (tenant-scoped).

    Respects the unread-dedupe unique constraint on ``(recipient, title)`` via
    ``get_or_create`` so a re-fired event doesn't raise IntegrityError on a row
    the recipient hasn't read yet.
    """
    if recipient is None or not getattr(recipient, "pk", None):
        return "no_recipient"
    title = (context.get("title") or "").strip()
    if not title:
        return "no_title"
    severity = context.get("severity") or Notification.Severity.INFO
    defaults = {
        "message": context.get("message", "") or "",
        "link": context.get("link", "") or "",
        "severity": severity,
        "school": school,
    }
    from django.db import IntegrityError

    try:
        obj, created = Notification.objects.get_or_create(
            recipient=recipient,
            title=title,
            is_read=False,
            defaults=defaults,
        )
        return "created" if created else "exists"
    except IntegrityError:
        # Race against the partial-unique unread constraint — treat as deduped.
        logger.debug("in-app notification dedup race", exc_info=True)
        return "exists"


def _send_email(notification_service, *, recipient, context, school, guardian):
    """Resolve the recipient email + send via the unified facade.

    Honours guardian ``receives_email`` when the recipient is a guardian. Email
    suppression itself is owned by the email-delivery reliability layer (see
    ``notification_service.send_email`` → ``schoolops.email_delivery``), so we do
    not re-check consent here.
    """
    if guardian is not None and not getattr(guardian, "receives_email", True):
        return "guardian_opt_out"
    address = (getattr(recipient, "email", "") or context.get("email") or "").strip()
    if not address:
        return "no_address"
    subject = (context.get("title") or "").strip() or "Notification"
    body = context.get("message", "") or ""
    return bool(
        notification_service.send_email(
            [address], subject, body, school=school,
        )
    )


def _send_sms(
    notification_service,
    is_channel_suppressed,
    *,
    recipient,
    context,
    school,
    guardian,
    pref,
):
    """Resolve phone + send SMS, honouring consent, guardian flag, quiet hours.

    * guardian ``receives_sms`` must be set when the recipient is a guardian;
    * an explicit STOP (consent withdrawal) suppresses the send;
    * inside the recipient's quiet-hours window we DEFER rather than send (honest
      ``"deferred_quiet_hours"`` so a digest job can pick it up in Phase 4).
    """
    if guardian is not None and not getattr(guardian, "receives_sms", False):
        return "guardian_opt_out"
    phone = (context.get("phone") or (getattr(guardian, "phone", "") if guardian else "") or "").strip()
    if not phone:
        return "no_phone"
    if is_channel_suppressed("sms", phone):
        return "suppressed"
    if pref is not None and pref.in_quiet_hours(_now_local_time(pref)):
        return "deferred_quiet_hours"
    body = context.get("message", "") or ""
    return bool(notification_service.send_sms(phone, body, school=school))


def _send_push(notification_service, web_push_service, *, recipient, context, school):
    """Native push (FCM/APNS) + best-effort web push — each isolated.

    Returns a small dict so a partial success (native ok, web push down) is
    reported honestly rather than collapsed to a single bool.
    """
    title = (context.get("title") or "").strip() or "Notification"
    body = context.get("message", "") or ""
    outcome: Dict[str, Any] = {}

    # Native push via the unified facade.
    try:
        outcome["native"] = bool(
            notification_service.send_push(school, recipient, title, body)
        )
    except Exception as exc:  # broad-by-design — isolate native from web push
        logger.debug("native push failed err=%s", type(exc).__name__, exc_info=True)
        outcome["native"] = f"error:{type(exc).__name__}"

    # Best-effort browser web push (only if the service is importable/configured).
    if web_push_service is not None:
        try:
            outcome["web"] = web_push_service.send_web_push_to_user(
                recipient,
                title=title,
                body=body,
                url=context.get("link", "") or "",
            )
        except Exception as exc:  # broad-by-design — web push never breaks native
            logger.debug("web push failed err=%s", type(exc).__name__, exc_info=True)
            outcome["web"] = f"error:{type(exc).__name__}"

    return outcome


__all__ = [
    "EVENT_CATEGORY_MAP",
    "DEFAULT_CATEGORY",
    "DEFAULT_CHANNELS_BY_CATEGORY",
    "category_for_event",
    "get_preference",
    "dispatch_event",
]
