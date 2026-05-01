"""
Dispatch hooks for school-domain workflow triggers (student, payment, grades, etc.).
"""

import logging

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

_DISPATCH_ERRORS = (
    ImportError,
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
)


def dispatch_payment_received_from_payment(payment) -> None:
    """Fire payment_received / payment_success school + tenant workflows after a payment is applied."""
    inv = getattr(payment, "invoice", None)
    school = getattr(payment, "school", None)
    if not school and inv is not None:
        school = getattr(inv, "school", None) or getattr(
            getattr(inv, "student", None), "school", None
        )
    if not school:
        return
    payload = {
        "payment_id": getattr(payment, "pk", None),
        "invoice_id": getattr(inv, "pk", None) if inv else None,
        "student_id": getattr(payment, "student_id", None)
        or (getattr(inv, "student_id", None) if inv else None),
        "amount": str(getattr(payment, "amount", "") or ""),
    }
    dispatch_domain_triggers_safe(school, "payment_received", payload)
    dispatch_domain_triggers_safe(school, "payment_success", payload)


def dispatch_domain_triggers_safe(school, trigger_type: str, context: dict) -> dict | None:
    """
    Run tenant catalog workflows + school automation workflows.
    Swallows engine errors so caller signals stay non-blocking.

    Enriches ``context`` with ``school_features`` (from ``school.features``) and
    ``school_id`` for condition ops ``feature_enabled`` / ``role_in``.
    """
    ctx = dict(context or {})
    try:
        feats = getattr(school, "features", None)
        if isinstance(feats, dict):
            ctx.setdefault("school_features", feats)
        sid = getattr(school, "pk", None)
        if sid is not None:
            ctx.setdefault("school_id", str(sid))
    except Exception:
        pass
    try:
        from .workflow_engine import dispatch_domain_triggers

        return dispatch_domain_triggers(school, trigger_type, ctx)
    except _DISPATCH_ERRORS as e:
        sid = str(getattr(school, "pk", None) or getattr(school, "id", ""))
        log_exception_with_context(
            "workflow_triggers: dispatch_domain_triggers failed",
            school_id=sid,
            extra={"trigger_type": trigger_type, "error": str(e)},
        )
        logger.debug("dispatch_domain_triggers skipped: %s", e)
        return None
