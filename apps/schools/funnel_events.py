"""
Marketing / growth conversion funnel event recording.
Supports anonymous (session+utm) and school-scoped events; idempotent "once" patterns per school.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError

from apps.schools.models import MarketingFunnelEvent

ALLOWED_EVENT_TYPES = frozenset(t[0] for t in MarketingFunnelEvent.EVENT_TYPES)

# Stages that should not duplicate per school (best-effort; race-safe under uniqueless DB).
_ONCE_PER_SCHOOL_TYPES = frozenset(
    {
        "onboarding_start",
        "onboarding_complete",
        "first_dashboard_view",
        "first_action",
        "first_result",
        "subscription_started",
        "signup_completed",
    }
)


def _utm_from_request(request) -> tuple[str, str]:
    get = getattr(request, "GET", None) or {}
    src = (get.get("utm_source") or "")[:128]
    med = (get.get("utm_medium") or "")[:128]
    return (src, med)


def _session_key(request) -> str:
    sk = getattr(request.session, "session_key", None) or ""
    return str(sk) if sk is not None else ""


def record_marketing_funnel_event(
    event_type: str,
    request,
    *,
    school=None,
    user=None,
    metadata: dict | None = None,
) -> None:
    """
    Record a funnel event. Extends legacy (visit, discovery, signup, activation) with
    growth stages. Pass school/user when known for closed-loop analytics.
    """
    if event_type not in ALLOWED_EVENT_TYPES:
        return
    utm_source, utm_medium = _utm_from_request(request)
    meta = dict(metadata or {})
    try:
        MarketingFunnelEvent.objects.create(
            event_type=event_type,
            session_key=_session_key(request),
            utm_source=utm_source,
            utm_medium=utm_medium,
            school=school if school is not None else None,
            user=user if user is not None else None,
            metadata=meta,
        )
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        pass


def record_school_funnel_once(
    event_type: str,
    school,
    request,
    *,
    user=None,
    metadata: dict | None = None,
) -> bool:
    """
    Record at most one row per (school, event_type) for once-per-tenant stages.
    Returns True if a new row was created.
    """
    if not school or event_type not in ALLOWED_EVENT_TYPES:
        return False
    if event_type in _ONCE_PER_SCHOOL_TYPES:
        if MarketingFunnelEvent.objects.filter(
            school_id=getattr(school, "pk", school),
            event_type=event_type,
        ).exists():
            return False
    record_marketing_funnel_event(
        event_type, request, school=school, user=user, metadata=metadata
    )
    return True


def record_first_action_signal(school, *, user=None, metadata: dict | None = None) -> bool:
    """Emit first_action funnel row without HTTP request (domain signals)."""
    if not school:
        return False
    if MarketingFunnelEvent.objects.filter(
        school_id=getattr(school, "pk", None),
        event_type="first_action",
    ).exists():
        return False
    meta = dict(metadata or {})
    try:
        MarketingFunnelEvent.objects.create(
            event_type="first_action",
            session_key="",
            utm_source="",
            utm_medium="",
            school=school,
            user=user if user is not None else None,
            metadata=meta,
        )
        return True
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        return False


def record_subscription_started_billing(
    school,
    *,
    subscription_id: int | None = None,
    billed_amount: str | None = None,
) -> None:
    """Billing hook: subscription row created — funnel marker + audit metadata (no HTTP request)."""
    if not school:
        return
    if MarketingFunnelEvent.objects.filter(
        school_id=getattr(school, "pk", None),
        event_type="subscription_started",
    ).exists():
        return
    meta: dict[str, Any] = {}
    if subscription_id:
        meta["tenant_subscription_id"] = subscription_id
    if billed_amount is not None:
        meta["billed_amount"] = str(billed_amount)
    try:
        MarketingFunnelEvent.objects.create(
            event_type="subscription_started",
            session_key="",
            utm_source="",
            utm_medium="",
            school=school,
            user=None,
            metadata=meta,
        )
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        pass


def try_record_first_result_payment(school, payment) -> None:
    """Finance hook: first recorded payment outcome at tenant (no HTTP request context)."""
    if not school:
        return
    if MarketingFunnelEvent.objects.filter(
        school_id=getattr(school, "pk", None),
        event_type="first_result",
    ).exists():
        return
    try:
        MarketingFunnelEvent.objects.create(
            event_type="first_result",
            session_key="",
            utm_source="",
            utm_medium="",
            school=school,
            user=None,
            metadata={
                "source": "finance_payment",
                "payment_id": getattr(payment, "pk", None),
            },
        )
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        pass


def try_record_first_result_report_output(
    school,
    *,
    report_card_id: int | None = None,
) -> None:
    """First operational report artifact at tenant (PDF report card)."""
    if not school:
        return
    if MarketingFunnelEvent.objects.filter(
        school_id=getattr(school, "pk", None),
        event_type="first_result",
    ).exists():
        return
    meta: dict[str, Any] = {"source": "report_output"}
    if report_card_id is not None:
        meta["report_card_id"] = report_card_id
    try:
        MarketingFunnelEvent.objects.create(
            event_type="first_result",
            session_key="",
            utm_source="",
            utm_medium="",
            school=school,
            user=None,
            metadata=meta,
        )
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        pass


def record_payment_outcome_signal(
    school,
    *,
    success: bool,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit payment_success or payment_failed; idempotent when processor_source_ref is present."""
    if not school:
        return
    event_type = "payment_success" if success else "payment_failed"
    if event_type not in ALLOWED_EVENT_TYPES:
        return
    meta = dict(metadata or {})
    meta.setdefault("funnel_stage", "revenue")
    ref = (
        str(meta.get("processor_source_ref") or meta.get("stripe_event_id") or "")
        .strip()
    )
    if ref:
        dup = MarketingFunnelEvent.objects.filter(
            school_id=getattr(school, "pk", None),
            event_type=event_type,
            metadata__processor_source_ref=ref,
        )
        if dup.exists():
            return
    try:
        MarketingFunnelEvent.objects.create(
            event_type=event_type,
            session_key="",
            utm_source="",
            utm_medium="",
            school=school,
            user=None,
            metadata=meta,
        )
    except (IntegrityError, DatabaseError, OperationalError, ValidationError, TypeError):
        pass
