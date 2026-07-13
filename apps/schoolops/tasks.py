"""v3.32.0 — Celery tasks for schoolops low-balance notification flow.

Two tasks:

* :func:`notify_low_meal_plan_balance` — point-shot delivery for a
  single :class:`MealPlanBalance` row that just transitioned False ->
  True. Idempotent via the 7-day cooldown on
  :attr:`MealPlanBalance.last_low_balance_notification_sent_at`.
* :func:`sweep_low_meal_plan_balances` — daily Celery-beat sweep that
  catches rows where the signal missed (e.g. rows that were already
  low when the signal was registered).

Logging contract:
  * NEVER log email, phone, names, balance numerics. Row PK + student
    ID + plan ID only.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


logger = logging.getLogger(__name__)

_LOW_BALANCE_COOLDOWN_DAYS = 7
_SWEEP_BATCH_LIMIT = 500
_SUPPORTED_LOCALES = ("en", "fr", "es", "pt", "ar")


def _resolve_guardian_locale(student) -> str:
    """Best-effort: return a 2-letter locale code based on the first
    eligible guardian's :attr:`User.preferred_language`. Falls back to
    ``"en"`` whenever the relation is missing or the language is unknown.

    NOTE: ``preferred_language`` is a column on the User model (added in
    accounts migration ``0031_add_preferred_language``); :class:`StudentGuardian`
    links to that user via ``guardian_user``.
    """
    try:
        # tenant-isolation-allow: guardian-link-row-scoped-via-student-fk-already-tenant-bound
        links = student.guardian_links.filter(receives_email=True)
    except Exception:  # noqa: BLE001
        return "en"
    for link in links:
        try:
            user = getattr(link, "guardian_user", None)
            if user is None:
                continue
            pref = (getattr(user, "preferred_language", "") or "").strip()
            if not pref:
                continue
            base = pref.lower().split("-", 1)[0].split("_", 1)[0]
            if base in _SUPPORTED_LOCALES:
                return base
        except Exception:  # noqa: BLE001
            continue
    return "en"


def _resolve_guardian_emails(student) -> list[str]:
    """Best-effort: return list of guardian email addresses for ``student``.

    Uses :class:`apps.people.models.StudentGuardian` (canonical link).
    Filters by ``receives_email=True`` so opted-out guardians are
    excluded. Never raises — returns an empty list when no guardian
    relation exists.
    """
    try:
        # tenant-isolation-allow: guardian-link-row-scoped-via-student-fk-already-tenant-bound
        links = student.guardian_links.filter(receives_email=True)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for link in links:
        try:
            email = (link.email or "").strip()
            if not email and link.guardian_user is not None:
                email = (link.guardian_user.email or "").strip()
            if email:
                out.append(email)
        except Exception:  # noqa: BLE001
            continue
    # De-dup preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for e in out:
        if e.lower() in seen:
            continue
        seen.add(e.lower())
        deduped.append(e)
    return deduped


def _maybe_dispatch_sms(student, body_text: str) -> bool:  # noqa: ARG001
    """Compatibility wrapper for v3.32 callers that pass a pre-rendered
    long-form body. v3.33 prefers :func:`_maybe_dispatch_sms_short_form`
    which renders the locale-specific short form and enforces the <=160
    char cap. Kept here so external callers don't break."""
    return _maybe_dispatch_sms_short_form(
        student=student, locale="en", first_name=getattr(student, "first_name", "") or "",
        balance=None, currency="",
    )


def _maybe_dispatch_sms_short_form(
    *,
    student,
    locale: str,
    first_name: str,
    balance,
    currency: str,
    school=None,
) -> bool:
    """Optional SMS hook. Returns True only if at least one SMS was sent.

    v3.33.0: locale-aware short-form body (<=160 chars). Privacy gate
    inside :func:`render_low_balance_sms` ensures we NEVER include the
    balance numeric when ``balance < $1`` (very-low form just says "low").

    Sends through the canonical notification facade
    :func:`apps.communication.notification_service.send_sms`, which threads
    consent / circuit-breaker / durable-enqueue internally. Mirrors the
    email half of the sweep: recipients are the student's guardian links
    filtered to the SMS channel (``receives_sms=True``, the SMS-channel
    analogue of the email path's ``receives_email=True``); the 7-day
    cooldown is enforced by the calling task BEFORE this hook runs, so we
    inherit the same gate. ``school`` is passed through so the facade keeps
    the sweep's tenant scoping (consent lookup, usage metering, circuit
    breaker are all school-scoped).

    Honest dispatch: returns True only when ``send_sms`` actually reports a
    send for at least one guardian — a falsy facade result is NOT counted.
    """
    from apps.schoolops.sms_templates import render_low_balance_sms

    body_text = render_low_balance_sms(
        locale=locale,
        first_name=first_name,
        balance=balance,
        currency=currency,
    )

    try:
        from apps.communication.notification_service import send_sms
        # tenant-isolation-allow: guardian-link-row-scoped-via-student-fk-already-tenant-bound
        links = student.guardian_links.filter(receives_sms=True)
        any_sent = False
        for link in links:
            phone = (getattr(link, "phone", "") or "").strip()
            if not phone:
                continue
            try:
                sent = send_sms(phone, body_text, school=school)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "schoolops.sms_dispatch failed student_id=%s",
                    getattr(student, "pk", None),
                )
                continue
            if sent:
                any_sent = True
        return any_sent
    except Exception:  # noqa: BLE001
        return False


@shared_task(name="schoolops.notify_low_meal_plan_balance")
def notify_low_meal_plan_balance(meal_plan_balance_id: int) -> dict[str, Any]:
    """Deliver low-balance notification for one :class:`MealPlanBalance` row.

    Idempotent: enforces 7-day cooldown via
    ``last_low_balance_notification_sent_at``. Returns a structured
    summary so test code can assert behavior without parsing logs.
    """
    result: dict[str, Any] = {
        "meal_plan_balance_id": int(meal_plan_balance_id),
        "delivered_email": False,
        "delivered_sms": False,
        "skipped_cooldown": False,
        "skipped_no_guardian_email": False,
        "skipped_not_low": False,
        "errors": 0,
    }
    try:
        from apps.schoolops.models import MealPlanBalance
        # tenant-isolation-allow: celery-task-fetch-by-pk-row-already-tenant-bound-via-school-fk
        row = MealPlanBalance.objects.filter(pk=meal_plan_balance_id).first()
        if row is None:
            result["errors"] += 1
            return result

        if not row.is_low:
            result["skipped_not_low"] = True
            return result

        # 7-day cooldown.
        last = row.last_low_balance_notification_sent_at
        if last is not None:
            try:
                if (timezone.now() - last).total_seconds() < (
                    _LOW_BALANCE_COOLDOWN_DAYS * 24 * 60 * 60
                ):
                    result["skipped_cooldown"] = True
                    return result
            except (TypeError, ValueError):
                pass

        student = row.student
        if student is None:
            result["skipped_no_guardian_email"] = True
            return result

        emails = _resolve_guardian_emails(student)
        if not emails:
            result["skipped_no_guardian_email"] = True
            # We still bump the timestamp so we don't pile on retries for
            # a row that structurally has no contact path.
            row.last_low_balance_notification_sent_at = timezone.now()
            row.save(
                update_fields=["last_low_balance_notification_sent_at"],
            )
            return result

        # Render templates. Note: subject contains FIRST NAME only — full
        # PII (last name, balance, plan label) lives in the body.
        first_name = (
            getattr(student, "first_name", "") or "Student"
        )
        ctx = {
            "student_first_name": first_name,
            "student_last_name": getattr(student, "last_name", "") or "",
            "balance_display": _format_money_display(
                row.balance, row.currency,
            ),
            "threshold_display": _format_money_display(
                row.low_balance_threshold, row.currency,
            ),
            "plan_label": (
                row.meal_plan.name if row.meal_plan is not None
                else "Cafeteria credit"
            ),
        }
        # v3.33.0: pick per-locale templates based on first eligible guardian's
        # preferred_language. Now routed through the shared locale-email renderer
        # (GAP-5) which owns the locale → fallback-locale → legacy-path cascade in
        # one place; ``rendered.locale`` is the locale that actually rendered, kept
        # so the downstream SMS stays in the same language.
        from apps.communication.email_locale import render_localized_email

        locale = _resolve_guardian_locale(student)
        subject = f"Low meal plan balance for {first_name}"
        rendered = render_localized_email(
            "schoolops/email", "low_meal_balance", locale, ctx
        )
        text_body = rendered.text
        html_body = rendered.html
        locale = rendered.locale

        from_email = getattr(
            settings, "DEFAULT_FROM_EMAIL", "no-reply@runmycampus.com",
        )
        try:
            send_mail(
                subject=subject,
                message=text_body,
                from_email=from_email,
                recipient_list=emails,
                html_message=html_body,
                fail_silently=False,
            )
            result["delivered_email"] = True
        except Exception:  # noqa: BLE001
            result["errors"] += 1
            logger.warning(
                "schoolops.low_balance_email_send_failed row_pk=%s "
                "student_id=%s",
                row.pk, getattr(student, "pk", None),
            )

        # Optional SMS — v3.33.0 short-form, locale-aware, with privacy
        # gate on critically-low balances (no numeric in plaintext when
        # balance < $1). NEVER reuse the long-form email body for SMS.
        sms_dispatched = _maybe_dispatch_sms_short_form(
            student=student,
            locale=locale,
            first_name=first_name,
            balance=row.balance,
            currency=row.currency,
            school=row.school,
        )
        result["delivered_sms"] = bool(sms_dispatched)
        result["locale"] = locale

        # Update tracking columns.
        row.last_low_balance_notification_sent_at = timezone.now()
        row.low_balance_notification_count = (
            (row.low_balance_notification_count or 0) + 1
        )
        row.save(update_fields=[
            "last_low_balance_notification_sent_at",
            "low_balance_notification_count",
        ])

        logger.info(
            "schoolops.low_balance_notification_dispatched "
            "row_pk=%s student_id=%s plan_id=%s status=low",
            row.pk,
            getattr(student, "pk", None),
            row.meal_plan_id,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result["errors"] += 1
        logger.exception(
            "schoolops.notify_low_meal_plan_balance crashed row_pk=%s "
            "exc_type=%s",
            meal_plan_balance_id, type(exc).__name__,
        )
        return result


def _format_money_display(amount, currency: str) -> str:
    """Render Decimal as plain string. NEVER float() money values."""
    if amount is None:
        return f"0.00 {currency or ''}".strip()
    # str() on a Decimal preserves precision; format separately by hand.
    return f"{amount} {currency or ''}".strip()


@shared_task(name="schoolops.sweep_low_meal_plan_balances")
def sweep_low_meal_plan_balances() -> dict[str, Any]:
    """Daily sweep: catch low rows the signal missed.

    Iterates :class:`MealPlanBalance` rows where ``status='active'`` and
    either (a) never notified or (b) cooldown has elapsed. For each
    row that is currently :attr:`is_low`, dispatches the point-shot
    task. Cooldown logic in the task itself prevents repeat sends.
    """
    summary: dict[str, Any] = {
        "scanned": 0,
        "enqueued": 0,
        "skipped_not_low": 0,
        "skipped_cooldown": 0,
        "errors": 0,
    }
    try:
        from apps.schoolops.models import MealPlanBalance
        cutoff = timezone.now() - _dt.timedelta(
            days=_LOW_BALANCE_COOLDOWN_DAYS,
        )
        # tenant-isolation-allow: sweep-task-runs-across-all-tenants-by-design-platform-wide-beat-job
        rows = MealPlanBalance.objects.filter(
            status="active",
        ).only(
            "pk", "balance", "low_balance_threshold",
            "last_low_balance_notification_sent_at",
        ).order_by("pk")[:_SWEEP_BATCH_LIMIT]

        from apps.schoolops.notification_batch import enqueue_in_chunks

        eligible_ids: list[int] = []
        for row in rows:
            summary["scanned"] += 1
            if not row.is_low:
                summary["skipped_not_low"] += 1
                continue
            last = row.last_low_balance_notification_sent_at
            if last is not None and last >= cutoff:
                summary["skipped_cooldown"] += 1
                continue
            eligible_ids.append(int(row.pk))

        try:
            batch_summary = enqueue_in_chunks(
                notify_low_meal_plan_balance,
                eligible_ids,
                max_total=_SWEEP_BATCH_LIMIT,
            )
            summary["enqueued"] = batch_summary["enqueued"]
            summary["skipped_cap"] = batch_summary.get("skipped_cap", 0)
        except Exception:  # noqa: BLE001
            summary["errors"] += 1
            logger.warning("schoolops.sweep_batch_enqueue_failed")
        logger.info(
            "schoolops.sweep_low_meal_plan_balances summary=%s", summary,
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        logger.exception(
            "schoolops.sweep_low_meal_plan_balances crashed exc_type=%s",
            type(exc).__name__,
        )
        return summary


# ──────────────────────────────────────────────────────────────────────
# v3.57.x Wave 8 Agent C — bulk email dispatch via Celery.
#
# Called by ``apps.schoolops.email_delivery.send_bulk`` when the caller
# wants the message off the request path. The task itself just calls
# ``send_transactional`` with priority="bulk" so the retry + audit
# semantics are identical on both paths.
# ──────────────────────────────────────────────────────────────────────


@shared_task(name="schoolops.dispatch_bulk_email")
def dispatch_bulk_email(
    *,
    subject: str,
    body: str,
    to: list,
    html_body: Any = None,
    reply_to: Any = None,
    from_email: Any = None,
    headers: Any = None,
    priority: str = "bulk",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Worker entry-point for ``send_bulk`` — runs ``send_transactional``.

    Returns the underlying send_transactional dict so the Celery result
    backend records the outcome. The send itself is best-effort —
    failures persist EmailDeliveryEvent rows for the operator dashboard.
    """
    try:
        from apps.schoolops.email_delivery import send_transactional

        return send_transactional(
            subject=subject,
            body=body,
            to=to,
            html_body=html_body,
            reply_to=reply_to,
            from_email=from_email,
            headers=headers,
            priority=priority or "bulk",
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001  — worker boundary
        logger.exception(
            "schoolops.dispatch_bulk_email crashed exc_type=%s",
            type(exc).__name__,
        )
        return {
            "ok": False,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": "task_crashed",
        }


@shared_task(name="schoolops.dispatch_transactional_email")
def dispatch_transactional_email(
    *,
    subject: str,
    body: str,
    to: Any,
    html_body: Any = None,
    reply_to: Any = None,
    from_email: Any = None,
    headers: Any = None,
    priority: str = "transactional",
    school: Any = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Durable worker entry-point for ``send_transactional(async_send=True)``.

    Audit C2 — when ``SCHOOLOPS_EMAIL_ASYNC_USE_CELERY`` is set (an always-on
    worker is available), async transactional sends route here instead of a
    daemon thread so they survive a web-worker restart. ``school`` is dropped
    on the wire (not JSON-serializable); the resolved SMTP config falls back
    to env/operator settings, which is correct for platform-level mail.
    """
    try:
        from apps.schoolops.email_delivery import send_transactional

        return send_transactional(
            subject=subject,
            body=body,
            to=to,
            html_body=html_body,
            reply_to=reply_to,
            from_email=from_email,
            headers=headers,
            priority=priority or "transactional",
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001  — worker boundary
        logger.exception(
            "schoolops.dispatch_transactional_email crashed exc_type=%s",
            type(exc).__name__,
        )
        return {
            "ok": False,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": "task_crashed",
        }


# ──────────────────────────────────────────────────────────────────────
# Metric 14 — inventory reorder (low-stock) alerts.
#
# Producer for :class:`apps.schoolops.models.InventoryItem`. When an item's
# stock crosses to/below its ``reorder_threshold`` (see the False -> True
# ``is_low`` transition detected by ``apps.schoolops.signals``), a WARNING
# notification is delivered to the school's admins via the canonical
# ``finance.Notification.objects.notify_unread`` write path. Idempotent per
# low-stock episode: ``notify_low_inventory_stock`` no-ops while
# ``last_low_stock_notified_at`` is set, and the signal clears that stamp when
# stock is replenished above the reorder level (so the NEXT dip re-fires).
# ──────────────────────────────────────────────────────────────────────

_LOW_STOCK_ADMIN_RECIPIENT_CAP = 20
# finance.Notification.title is a CharField(max_length=200); truncate to match.
_NOTIF_TITLE_MAXLEN = 200  # magic-number-allow: notification-title-column-max-length


def _school_admin_recipients(school) -> list:
    """Active ADMIN users for ``school`` (canonical SchoolMembership lookup)."""
    if school is None:
        return []
    try:
        from apps.schools.models import SchoolMembership
    except Exception:  # noqa: BLE001
        return []
    recipients: list = []
    seen: set = set()
    qs = (
        # tenant-isolation-allow: low-inventory-recipients-are-scoped-by-school-membership
        SchoolMembership.objects.filter(
            school=school, role="ADMIN",  # role-string-allow: notify-school-admins-of-low-inventory-stock
        )
        .select_related("user")
        .order_by("-is_primary", "id")[:_LOW_STOCK_ADMIN_RECIPIENT_CAP]
    )
    for membership in qs:
        user = getattr(membership, "user", None)
        if user is None or not getattr(user, "is_active", True):
            continue
        if user.pk in seen:
            continue
        seen.add(user.pk)
        recipients.append(user)
    return recipients


@shared_task(name="schoolops.notify_low_inventory_stock")
def notify_low_inventory_stock(inventory_item_id: int) -> dict[str, Any]:
    """Deliver a low-stock alert for one :class:`InventoryItem` row.

    Idempotent per low-stock episode: skips when the row is no longer low or
    when ``last_low_stock_notified_at`` is already set (the signal clears that
    stamp on replenishment above the reorder level). Returns a structured
    summary so tests can assert behaviour without parsing logs.
    """
    result: dict[str, Any] = {
        "inventory_item_id": int(inventory_item_id),
        "notified_recipients": 0,
        "skipped_not_low": False,
        "skipped_already_notified": False,
        "skipped_no_recipients": False,
        "errors": 0,
    }
    try:
        from django.db.models import F
        from django.urls import reverse

        from apps.finance.models import Notification
        from apps.schoolops.models import InventoryItem

        # tenant-isolation-allow: celery-task-fetch-by-pk-row-already-tenant-bound-via-school-fk
        row = (
            InventoryItem.objects.filter(pk=inventory_item_id)
            .select_related("school")
            .first()
        )
        if row is None:
            result["errors"] += 1
            return result
        if not row.is_low:
            result["skipped_not_low"] = True
            return result
        if row.last_low_stock_notified_at is not None:
            # Already alerted for the current low-stock episode.
            result["skipped_already_notified"] = True
            return result

        recipients = _school_admin_recipients(row.school)
        if not recipients:
            result["skipped_no_recipients"] = True
            # Still stamp so the sweep doesn't retry a structurally-unreachable
            # row every run; a later membership change + restock re-opens it.
            # tenant-isolation-allow: stamp-scoped-to-same-row-and-its-school-fk
            InventoryItem.objects.filter(
                pk=row.pk, school_id=row.school_id,
            ).update(last_low_stock_notified_at=timezone.now())
            return result

        location = (row.location or "").strip() or "—"
        title = (f"Low stock: {row.name}")[:_NOTIF_TITLE_MAXLEN]
        message = (
            f"{row.name} is at {row.quantity} "
            f"(reorder level {row.reorder_threshold}) in {location}. "
            f"Restock to clear this alert."
        )
        try:
            link = reverse("accounts:ops_inventory")
        except Exception:  # noqa: BLE001
            link = ""

        notified = 0
        for user in recipients:
            try:
                Notification.objects.notify_unread(
                    recipient=user,
                    title=title,
                    message=message,
                    severity=Notification.Severity.WARNING,
                    link=link,
                    school=row.school,
                )
                notified += 1
            except Exception:  # noqa: BLE001 — per-recipient isolation
                result["errors"] += 1
                logger.warning(
                    "schoolops.low_inventory_notify_failed item_id=%s",
                    row.pk,
                )
        result["notified_recipients"] = notified

        # Stamp + bump count so the episode is closed (idempotent). Queryset
        # update bypasses signals — no re-entrancy.
        # tenant-isolation-allow: stamp-scoped-to-same-row-and-its-school-fk
        InventoryItem.objects.filter(pk=row.pk, school_id=row.school_id).update(
            last_low_stock_notified_at=timezone.now(),
            low_stock_notification_count=F("low_stock_notification_count") + 1,
        )
        logger.info(
            "schoolops.low_inventory_notification_dispatched "
            "item_id=%s school_id=%s recipients=%s",
            row.pk, row.school_id, notified,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result["errors"] += 1
        logger.exception(
            "schoolops.notify_low_inventory_stock crashed item_id=%s exc_type=%s",
            inventory_item_id, type(exc).__name__,
        )
        return result


@shared_task(name="schoolops.sweep_low_inventory_stock")
def sweep_low_inventory_stock() -> dict[str, Any]:
    """Daily sweep: alert on low-stock rows the signal missed.

    Catches items that were already low before the feature shipped (or whose
    transition signal did not fire). Only rows with a positive reorder level,
    ``quantity <= reorder_threshold``, and no open alert
    (``last_low_stock_notified_at IS NULL``) are enqueued — so it never
    double-fires an episode already alerted.
    """
    summary: dict[str, Any] = {
        "scanned": 0,
        "enqueued": 0,
        "errors": 0,
    }
    try:
        from django.db.models import F

        from apps.schoolops.models import InventoryItem

        # tenant-isolation-allow: sweep-task-runs-across-all-tenants-by-design-platform-wide-beat-job
        rows = (
            InventoryItem.objects.filter(
                reorder_threshold__gt=0,
                quantity__lte=F("reorder_threshold"),
                last_low_stock_notified_at__isnull=True,
            )
            .only("pk")
            .order_by("pk")[:_SWEEP_BATCH_LIMIT]
        )
        eligible_ids = [int(r.pk) for r in rows]
        summary["scanned"] = len(eligible_ids)
        for item_id in eligible_ids:
            try:
                notify_low_inventory_stock.delay(inventory_item_id=item_id)
            except Exception:  # noqa: BLE001 — free tier has no broker
                notify_low_inventory_stock(inventory_item_id=item_id)
            summary["enqueued"] += 1
        logger.info("schoolops.sweep_low_inventory_stock summary=%s", summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        logger.exception(
            "schoolops.sweep_low_inventory_stock crashed exc_type=%s",
            type(exc).__name__,
        )
        return summary


@shared_task(name="schoolops.deliver_notification_intent")
def deliver_notification_intent_task(
    *,
    school_id: int,
    subject: str,
    body: str,
    to_hash_target: str,
    to_email: str,
    html_body: str | None = None,
    idempotency_key: str = "",
    tenant_hash: str = "",
) -> dict[str, Any]:
    """Async path for SODP notification intents (never logs raw recipient)."""
    try:
        from apps.schoolops.email_delivery import send_transactional
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "error": "school_not_found"}
        return send_transactional(
            subject=subject,
            body=body,
            to=to_email,
            html_body=html_body,
            async_send=False,
            tenant_hash=tenant_hash or None,
            school=school,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "schoolops.deliver_notification_intent failed school_id=%s to_hash=%s err_type=%s",
            school_id,
            to_hash_target,
            type(exc).__name__,
        )
        return {"ok": False, "error_kind": "task_crashed"}
