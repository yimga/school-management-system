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
from django.template.loader import render_to_string
from django.utils import timezone


logger = logging.getLogger(__name__)

_LOW_BALANCE_COOLDOWN_DAYS = 7
_SWEEP_BATCH_LIMIT = 500


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


def _maybe_dispatch_sms(student, body_text: str) -> bool:
    """Optional SMS hook. Returns True on dispatch, False otherwise.

    Looks for ``apps.notifications.sms_helpers.send_sms`` or
    ``apps.communication.sms_helpers.send_sms`` (either may exist in
    different waves of this repo); if neither importable, no-op.
    """
    try:
        from importlib import import_module
        for mod_path in (
            "apps.notifications.sms_helpers",
            "apps.communication.sms_helpers",
        ):
            try:
                mod = import_module(mod_path)
            except ImportError:
                continue
            send_sms = getattr(mod, "send_sms", None)
            if not callable(send_sms):
                continue
            # tenant-isolation-allow: sms-helper-resolves-recipient-via-student-fk-tenant-graph
            links = student.guardian_links.filter(
                receives_sms=True,
            )
            for link in links:
                phone = (getattr(link, "phone", "") or "").strip()
                if not phone:
                    continue
                try:
                    send_sms(phone, body_text)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "schoolops.sms_dispatch failed student_id=%s",
                        getattr(student, "pk", None),
                    )
            return True
    except Exception:  # noqa: BLE001
        return False
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
        subject = f"Low meal plan balance for {first_name}"
        text_body = render_to_string(
            "schoolops/email/low_meal_balance.txt", ctx,
        )
        html_body = render_to_string(
            "schoolops/email/low_meal_balance.html", ctx,
        )

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

        # Optional SMS.
        sms_dispatched = _maybe_dispatch_sms(student, text_body)
        result["delivered_sms"] = bool(sms_dispatched)

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

        for row in rows:
            summary["scanned"] += 1
            if not row.is_low:
                summary["skipped_not_low"] += 1
                continue
            last = row.last_low_balance_notification_sent_at
            if last is not None and last >= cutoff:
                summary["skipped_cooldown"] += 1
                continue
            try:
                notify_low_meal_plan_balance.delay(
                    meal_plan_balance_id=int(row.pk),
                )
                summary["enqueued"] += 1
            except Exception:  # noqa: BLE001
                summary["errors"] += 1
                logger.warning(
                    "schoolops.sweep_enqueue_failed row_pk=%s", row.pk,
                )
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
