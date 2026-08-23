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
# Per-SCHOOL cap. It used to cap one query across every tenant's rows at once,
# which let a single large school starve every other one of its daily sweep.
_SWEEP_BATCH_LIMIT = 500
_SUPPORTED_LOCALES = ("en", "fr", "es", "pt", "ar")


def _with_tenant(school_id, fn, /, **kwargs):
    """Run ``fn(**kwargs)`` inside the tenant context for ``school_id``.

    Both leading parameters are POSITIONAL-ONLY. The per-school sweep bodies
    take their own ``school_id`` kwarg -- naming these would make
    ``_with_tenant(sid, fn, school_id=sid)`` a "multiple values for argument"
    TypeError, which the callers' ``except Exception`` would file as a per-tenant
    failure rather than surfacing.

    A Celery worker carries NO tenant context. It has no request, no tenant
    middleware and no URL host to resolve from, so its connection sits on the
    ``public`` schema for the whole task. ``apps.schoolops`` is in TENANT_APPS
    only (config/settings.py), which means under ``USE_DJANGO_TENANTS`` its
    tables exist *exclusively* inside tenant schemas -- a model query issued
    from the worker without this wrapper resolves against ``public``, where the
    relation does not exist, and raises ProgrammingError. These tasks each wrap
    their body in ``except Exception``, so that lands as ``errors += 1`` and a
    log line: the sweep then reports a clean zero-work run, forever.

    Under RLS mode (the sovereign edge boxes: one schema, many schools) the
    failure is quieter and worse -- the query succeeds against whatever the
    session GUC happens to be, with no school scoping of its own.

    Returns whatever ``fn`` returns; propagates ValueError when the tenant
    cannot be resolved, which the sweeps count per school rather than aborting.
    """
    from apps.schools.celery_tasks import _run_with_tenant_context

    return _run_with_tenant_context(
        school_id=str(school_id), runnable=lambda: fn(**kwargs)
    )


def _sweep_target_school_ids(school_id=None) -> list:
    """School ids a beat-driven sweep should visit (one, or every active one)."""
    if school_id is not None:
        return [school_id]
    from apps.schools.celery_tasks import get_active_school_ids

    return list(get_active_school_ids())


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
        links = student.guardian_links.filter(is_active=True, receives_email=True)
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
        links = student.guardian_links.filter(is_active=True, receives_email=True)
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
        links = student.guardian_links.filter(is_active=True, receives_sms=True)
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
def notify_low_meal_plan_balance(
    meal_plan_balance_id: int, school_id: str | None = None
) -> dict[str, Any]:
    """Deliver low-balance notification for one :class:`MealPlanBalance` row.

    Idempotent: enforces 7-day cooldown via
    ``last_low_balance_notification_sent_at``. Returns a structured
    summary so test code can assert behavior without parsing logs.

    ``school_id`` is what makes this safe to enqueue. Callers already inside a
    request (the signal path) run in tenant context, but ``.delay()`` hands the
    row pk to a worker that has none -- see :func:`_with_tenant`. Pass the
    row's ``school_id`` and the body runs against the right schema. It stays
    optional so a direct in-context call is unchanged.
    """
    if school_id is not None:
        return _with_tenant(
            school_id,
            notify_low_meal_plan_balance,
            meal_plan_balance_id=meal_plan_balance_id,
        )
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


def _sweep_low_meal_plan_balances_for_school(school_id) -> dict[str, Any]:
    """One school's low-balance sweep. Runs INSIDE that school's tenant context."""
    summary: dict[str, Any] = {
        "scanned": 0,
        "enqueued": 0,
        "skipped_not_low": 0,
        "skipped_cooldown": 0,
        "skipped_cap": 0,
        "errors": 0,
    }
    try:
        from apps.schoolops.models import MealPlanBalance
        cutoff = timezone.now() - _dt.timedelta(
            days=_LOW_BALANCE_COOLDOWN_DAYS,
        )
        # school_id is belt-and-braces on top of the tenant context: in RLS
        # mode every school shares one table, so this filter -- not the schema
        # -- is what keeps one school's sweep out of another's rows.
        rows = MealPlanBalance.objects.filter(
            school_id=school_id,
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
                school_id=str(school_id),
            )
            summary["enqueued"] = batch_summary["enqueued"]
            summary["skipped_cap"] = batch_summary.get("skipped_cap", 0)
        except Exception:  # noqa: BLE001
            summary["errors"] += 1
            logger.warning(
                "schoolops.sweep_batch_enqueue_failed school_id=%s", school_id
            )
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        logger.exception(
            "schoolops.sweep_low_meal_plan_balances crashed school_id=%s "
            "exc_type=%s",
            school_id,
            type(exc).__name__,
        )
        return summary


@shared_task(name="schoolops.sweep_low_meal_plan_balances")
def sweep_low_meal_plan_balances(school_id: str | None = None) -> dict[str, Any]:
    """Daily sweep: catch low rows the signal missed.

    Visits every active school IN ITS OWN TENANT CONTEXT and, for each,
    iterates :class:`MealPlanBalance` rows where ``status='active'`` and either
    (a) never notified or (b) cooldown has elapsed. Rows currently
    :attr:`is_low` get the point-shot task, which is itself idempotent via the
    cooldown, so a repeat sweep never double-sends.

    The per-school loop is not a refinement, it is the whole thing working: this
    is a beat job on a worker with no tenant context, and ``apps.schoolops`` is
    TENANT_APPS-only, so a single un-wrapped query ran against ``public`` --
    where the table does not exist -- and was swallowed by the ``except`` below.
    See :func:`_with_tenant`.

    ``school_id`` runs a single school, for operators and tests.
    """
    summary: dict[str, Any] = {
        "schools": 0,
        "schools_failed": 0,
        "scanned": 0,
        "enqueued": 0,
        "skipped_not_low": 0,
        "skipped_cooldown": 0,
        "skipped_cap": 0,
        "errors": 0,
    }
    for sid in _sweep_target_school_ids(school_id):
        summary["schools"] += 1
        try:
            one = (
                _with_tenant(
                    sid, _sweep_low_meal_plan_balances_for_school, school_id=sid
                )
                or {}
            )
        except Exception as exc:  # noqa: BLE001 - one bad tenant must not end the sweep
            summary["errors"] += 1
            summary["schools_failed"] += 1
            logger.exception(
                "schoolops.sweep_low_meal_plan_balances tenant_context_failed "
                "school_id=%s exc_type=%s",
                sid,
                type(exc).__name__,
            )
            continue
        for key, value in one.items():
            summary[key] = summary.get(key, 0) + value
    logger.info(
        "schoolops.sweep_low_meal_plan_balances summary=%s", summary,
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
    school_id: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Worker entry-point for ``send_bulk`` — runs ``send_transactional``.

    Returns the underlying send_transactional dict so the Celery result
    backend records the outcome. The send itself is best-effort —
    failures persist EmailDeliveryEvent rows for the operator dashboard.

    ``school_id``, when the caller supplies it, puts the send inside that
    school's tenant context: the worker has none of its own, and
    EmailDeliveryEvent is TENANT_APPS-only. See
    :func:`dispatch_transactional_email`.
    """
    def _run(resolved_school=None) -> dict[str, Any]:
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
            school=resolved_school,
            idempotency_key=idempotency_key,
        )

    try:
        sid = str(school_id or "").strip()
        if not sid:
            return _run()

        def _resolved():
            from apps.schools.models import School

            # School is the tenant root, in the SHARED schema.
            return _run(School.objects.filter(pk=sid).first())  # tenant-isolation-allow: school-is-the-tenant-root (pk IS the tenant key, and the call already runs inside _with_tenant(sid))

        return _with_tenant(sid, _resolved) or {}
    except Exception as exc:  # noqa: BLE001  — worker boundary
        logger.exception(
            "schoolops.dispatch_bulk_email crashed school_id=%s exc_type=%s",
            school_id or "",
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
    school_id: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Durable worker entry-point for ``send_transactional(async_send=True)``.

    Audit C2 — when ``SCHOOLOPS_EMAIL_ASYNC_USE_CELERY`` is set (an always-on
    worker is available), async transactional sends route here instead of a
    daemon thread so they survive a web-worker restart.

    ``school_id`` (not ``school``) is what crosses the wire. The broker
    serializer is JSON, so a School instance raised EncodeError at
    ``.delay()`` and the caller silently fell back to the daemon thread --
    meaning the durable path never ran for any send that named a school, which
    is the only kind it was built for. The id is re-resolved here, inside the
    tenant context, which also restores the per-tenant SMTP override the old
    docstring recorded as unavoidably lost.

    ``school`` is still accepted, and ignored, so an old in-flight message
    cannot fail with an unexpected-keyword TypeError.
    """
    def _run(resolved_school=None) -> dict[str, Any]:
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
            school=resolved_school,
            idempotency_key=idempotency_key,
        )

    try:
        sid = str(school_id or "").strip()
        if not sid:
            # Platform-level mail: no tenant to enter, same as before.
            return _run()

        def _resolved():
            from apps.schools.models import School

            # School is the tenant root and lives in the SHARED schema; a pk
            # lookup is not itself a tenant-scoped read.
            return _run(School.objects.filter(pk=sid).first())  # tenant-isolation-allow: school-is-the-tenant-root (pk IS the tenant key, and the call already runs inside _with_tenant(sid))

        return _with_tenant(sid, _resolved) or {}
    except Exception as exc:  # noqa: BLE001  — worker boundary
        logger.exception(
            "schoolops.dispatch_transactional_email crashed school_id=%s exc_type=%s",
            school_id or "",
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
        # `school` is the low-stock item's own tenant (guarded non-None above), so
        # this is tenant-scoped; keep `school=` on the .filter( line so the
        # celery-tenant-scope gate can see the scoping (audit_celery_tenant_task_scoping).
        SchoolMembership.objects.filter(school=school, role="ADMIN")  # role-string-allow: notify-school-admins-of-low-inventory-stock
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
def notify_low_inventory_stock(
    inventory_item_id: int, school_id: str | None = None
) -> dict[str, Any]:
    """Deliver a low-stock alert for one :class:`InventoryItem` row.

    Idempotent per low-stock episode: skips when the row is no longer low or
    when ``last_low_stock_notified_at`` is already set (the signal clears that
    stamp on replenishment above the reorder level). Returns a structured
    summary so tests can assert behaviour without parsing logs.

    ``school_id`` puts the body in tenant context; see
    :func:`notify_low_meal_plan_balance` for why an enqueued call needs it.
    """
    if school_id is not None:
        return _with_tenant(
            school_id,
            notify_low_inventory_stock,
            inventory_item_id=inventory_item_id,
        )
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


def _sweep_low_inventory_stock_for_school(school_id) -> dict[str, Any]:
    """One school's low-stock sweep. Runs INSIDE that school's tenant context."""
    summary: dict[str, Any] = {
        "scanned": 0,
        "enqueued": 0,
        "errors": 0,
    }
    try:
        from django.db.models import F

        from apps.schoolops.models import InventoryItem

        # school_id is belt-and-braces on top of the tenant context: in RLS
        # mode every school shares one table, so this filter -- not the schema
        # -- is what keeps one school's sweep out of another's rows.
        rows = (
            InventoryItem.objects.filter(
                school_id=school_id,
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
                notify_low_inventory_stock.delay(
                    inventory_item_id=item_id, school_id=str(school_id)
                )
            except Exception:  # noqa: BLE001 — free tier has no broker
                # Inline, and already inside this school's context, so the
                # school_id round-trip would be redundant work.
                notify_low_inventory_stock(inventory_item_id=item_id)
            summary["enqueued"] += 1
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        logger.exception(
            "schoolops.sweep_low_inventory_stock crashed school_id=%s exc_type=%s",
            school_id,
            type(exc).__name__,
        )
        return summary


@shared_task(name="schoolops.sweep_low_inventory_stock")
def sweep_low_inventory_stock(school_id: str | None = None) -> dict[str, Any]:
    """Daily sweep: alert on low-stock rows the signal missed.

    Visits every active school IN ITS OWN TENANT CONTEXT. Catches items that
    were already low before the feature shipped (or whose transition signal did
    not fire). Only rows with a positive reorder level,
    ``quantity <= reorder_threshold``, and no open alert
    (``last_low_stock_notified_at IS NULL``) are enqueued — so it never
    double-fires an episode already alerted.

    On the per-school loop, see :func:`sweep_low_meal_plan_balances`: this runs
    on a Celery worker with no tenant context, against TENANT_APPS-only tables.

    ``school_id`` runs a single school, for operators and tests.
    """
    summary: dict[str, Any] = {
        "schools": 0,
        "schools_failed": 0,
        "scanned": 0,
        "enqueued": 0,
        "errors": 0,
    }
    for sid in _sweep_target_school_ids(school_id):
        summary["schools"] += 1
        try:
            one = (
                _with_tenant(
                    sid, _sweep_low_inventory_stock_for_school, school_id=sid
                )
                or {}
            )
        except Exception as exc:  # noqa: BLE001 - one bad tenant must not end the sweep
            summary["errors"] += 1
            summary["schools_failed"] += 1
            logger.exception(
                "schoolops.sweep_low_inventory_stock tenant_context_failed "
                "school_id=%s exc_type=%s",
                sid,
                type(exc).__name__,
            )
            continue
        for key, value in one.items():
            summary[key] = summary.get(key, 0) + value
    logger.info("schoolops.sweep_low_inventory_stock summary=%s", summary)
    return summary


@shared_task(name="schoolops.run_procurement_scan")
def run_procurement_scan_task(school_id: int) -> dict[str, Any]:
    """School-scoped reorder scan with live workflow telemetry."""
    from apps.schools.celery_tasks import _run_with_tenant_context

    def _run() -> dict[str, Any]:
        from apps.schoolops.procurement_loop import run_school_procurement_scan
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "error": "school_not_found", "scanned": 0, "low": 0}
        return run_school_procurement_scan(school)

    try:
        return _run_with_tenant_context(school_id=str(school_id), runnable=_run) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "schoolops.run_procurement_scan tenant_context_failed school=%s err=%s",
            school_id,
            type(exc).__name__,
        )
        return _run()


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


# ──────────────────────────────────────────────────────────────────────
# W24 — structured immunization records + missing-vaccine alert sweep.
#
# Per-school sweep mirroring ``apps.people.tasks.check_badge_expiry_alerts_task``
# (per-school tenant context via ``_run_with_tenant_context`` /
# ``get_active_school_ids``). For each active student that is NOT compliant with
# the tenant's ``VaccineRequirement`` schedule, a WARNING ``finance.Notification``
# is delivered to the student's guardians via ``notify_unread`` — the same
# guardian-resolution path as ``_notify_guardians_of_rollover``.
#
# PII posture (matches the meal-plan / inventory tasks in this module): the
# alert names the child's FIRST NAME only — never a vaccine list, a dose count,
# or any health detail — and every log line carries ids only. Emission is
# best-effort per guardian and per student (a failure never breaks the sweep),
# mirroring the rollover notify posture.
# ──────────────────────────────────────────────────────────────────────

_IMMUNIZATION_SWEEP_STUDENT_CAP = 2000
# finance.Notification.title is a CharField(max_length=200).
_IMMUNIZATION_ALERT_TITLE = "Immunization records incomplete"


def _emit_missing_immunization_alerts(student, school) -> int:
    """Deliver one WARNING notification per active guardian of ``student``.

    PII-safe: the message names the child's first name only. Returns the number
    of notifications created. Never raises — mirrors the rollover best-effort
    posture so one bad recipient can't abort the sweep.
    """
    from apps.finance.models import Notification

    first_name = (getattr(student, "first_name", "") or "").strip() or "your child"
    message = (
        f"One or more required immunization records are missing for "
        f"{first_name}. Please contact the school health office to update "
        f"the record."
    )
    raised = 0
    try:
        # tenant-isolation-allow: guardian-link-row-scoped-via-student-fk-already-tenant-bound
        links = student.guardian_links.filter(is_active=True).select_related(
            "guardian_user"
        )
    except Exception:  # noqa: BLE001
        return 0
    for link in links:
        guardian_user_id = getattr(link, "guardian_user_id", None)
        if not guardian_user_id:
            continue
        try:
            Notification.objects.notify_unread(
                title=_IMMUNIZATION_ALERT_TITLE,
                message=message,
                severity=Notification.Severity.WARNING,
                recipient_id=guardian_user_id,
                school=school,
            )
            raised += 1
        except Exception:  # noqa: BLE001 — per-recipient isolation
            logger.warning(
                "schoolops.immunization_alert_failed student_id=%s",
                getattr(student, "pk", None),
            )
    return raised


def _run_missing_immunizations_sweep_for_school(school) -> dict[str, Any]:
    """Sweep one school's active students; alert guardians of non-compliant ones.

    Returns a small summary dict. Never raises. Behaviour-preserving: a school
    with no ``VaccineRequirement`` rows has nothing to enforce, so its students
    are never touched.
    """
    summary: dict[str, Any] = {
        "school_id": getattr(school, "pk", None),
        "students_checked": 0,
        "students_noncompliant": 0,
        "alerts_raised": 0,
        "errors": 0,
    }
    if school is None:
        return summary
    try:
        from apps.people.models import StudentProfile
        from apps.schoolops.immunization import (
            compute_missing_immunizations,
            resolve_vaccine_requirements,
        )

        if not resolve_vaccine_requirements(school):
            return summary

        students = (
            StudentProfile.objects.filter(
                school=school, is_active=True, deleted_at__isnull=True
            )
            .only("id", "first_name")
            .order_by("id")[:_IMMUNIZATION_SWEEP_STUDENT_CAP]
        )
        for student in students:
            summary["students_checked"] += 1
            try:
                status = compute_missing_immunizations(student, school)
            except Exception:  # noqa: BLE001 — per-student isolation
                summary["errors"] += 1
                logger.warning(
                    "schoolops.immunization_compute_failed student_id=%s",
                    getattr(student, "pk", None),
                )
                continue
            if status.get("is_compliant", True):
                continue
            summary["students_noncompliant"] += 1
            summary["alerts_raised"] += _emit_missing_immunization_alerts(
                student, school
            )
        logger.info(
            "schoolops.missing_immunizations_sweep school_id=%s checked=%s "
            "noncompliant=%s alerts=%s",
            summary["school_id"],
            summary["students_checked"],
            summary["students_noncompliant"],
            summary["alerts_raised"],
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        logger.exception(
            "schoolops.missing_immunizations_sweep crashed school_id=%s exc_type=%s",
            getattr(school, "pk", None),
            type(exc).__name__,
        )
        return summary


@shared_task(bind=True, name="schoolops.check_missing_immunizations")
def check_missing_immunizations_task(
    self, school_id: str | None = None
) -> dict[str, Any]:
    """W24 — per-school missing-immunization alert sweep.

    Mirrors :func:`apps.people.tasks.check_badge_expiry_alerts_task`: runs the
    sweep in tenant context per school (or across all active schools when
    ``school_id`` is None). Returns an aggregate summary dict.
    """
    from apps.schools.celery_tasks import (
        _run_with_tenant_context,
        get_active_school_ids,
    )

    def _run_one(sid):
        from apps.schools.models import School

        # School is the tenant root (SHARED); a pk lookup is not tenant-scoped.
        school = School.objects.filter(pk=sid).first()
        return _run_missing_immunizations_sweep_for_school(school)

    if school_id is not None:
        return (
            _run_with_tenant_context(
                school_id=school_id, runnable=lambda: _run_one(school_id)
            )
            or {}
        )

    totals: dict[str, Any] = {
        "schools": 0,
        "students_checked": 0,
        "students_noncompliant": 0,
        "alerts_raised": 0,
    }
    for sid in get_active_school_ids():
        one = (
            _run_with_tenant_context(
                school_id=sid, runnable=lambda s=sid: _run_one(s)
            )
            or {}
        )
        totals["schools"] += 1
        totals["students_checked"] += one.get("students_checked", 0)
        totals["students_noncompliant"] += one.get("students_noncompliant", 0)
        totals["alerts_raised"] += one.get("alerts_raised", 0)
    return totals
