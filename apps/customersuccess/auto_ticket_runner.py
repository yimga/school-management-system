"""Move 4 — actually run AutoTicketRule rows.

A periodic Celery task or management command iterates AutoTicketRule rows
and for each rule that triggers it creates a FeedbackSubmission (the
project's canonical support-ticket equivalent) flagged with
``source="auto_ticket_rule"``.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Stamped on every auto-ticket so the dedup prefilter can hit an indexed column.
AUTO_TICKET_MODULE = "customersuccess.auto_ticket"


def _already_opened(FeedbackSubmission, *, school, dedupe_key: str) -> bool:
    """True when this (rule, source row) already has a ticket.

    The beat runs every 10 minutes while the rules select over a 24-hour window,
    so without this every matching row would re-open the same ticket 144 times a
    day. ``tags`` is a JSONField and the ``__contains`` lookup is unsupported on
    SQLite, so prefilter on the indexed columns and match in Python.
    """
    rows = FeedbackSubmission.objects.filter(
        school=school, module=AUTO_TICKET_MODULE
    ).only("tags")
    return any(dedupe_key in (row.tags or []) for row in rows)


def _open_ticket(
    *,
    school,
    title: str,
    body: str,
    source: str = "auto_ticket_rule",
    dedupe_key: str = "",
) -> bool:
    """Create a FeedbackSubmission as the auto-ticket; safe across the
    edge cases where feedback isn't installed yet.

    ``dedupe_key`` identifies the (rule, source row) pair. When supplied and a
    ticket already carries it, nothing is written and False is returned — the
    caller counts tickets OPENED, so a suppressed duplicate is not a firing.
    """

    try:
        from apps.feedback.models import FeedbackSubmission
    except Exception:
        logger.warning("AutoTicketRule fired but feedback app not available.")
        return False
    try:
        tags = [source, "auto_ticket"]
        if dedupe_key:
            if _already_opened(
                FeedbackSubmission, school=school, dedupe_key=dedupe_key
            ):
                return False
            tags.append(dedupe_key)
        FeedbackSubmission.objects.create(
            school=school,
            user=None,
            title=title[:180],
            description=body[:4000],
            category=FeedbackSubmission.Category.GENERAL,
            severity=FeedbackSubmission.Severity.HIGH,
            status=FeedbackSubmission.Status.NEW,
            privacy_level=FeedbackSubmission.PrivacyLevel.RMC_PRIVATE,
            module=AUTO_TICKET_MODULE,
            tags=tags,
        )
        return True
    except Exception as exc:
        logger.warning("AutoTicketRule could not write FeedbackSubmission: %s", exc)
        return False


DEFAULT_HEALTH_BELOW_THRESHOLD = 50  # magic-number-allow: auto-ticket health floor


def rule_threshold(rule) -> int:
    """``config['threshold']`` as an int, or the default when it is not one.

    ``AutoTicketRule.config`` is a plain JSONField with no shape validation on
    the model, and the operator UI only checks that the blob is a dict -- so
    ``{"threshold": "high"}`` persists happily through both the UI and the
    Django admin. A bare ``int()`` on that raised ValueError out of the rule
    evaluator, and the runner's single outer transaction then rolled back every
    ticket the OTHER rules had already opened in the same pass.
    """
    config = getattr(rule, "config", None)
    raw = config.get("threshold") if isinstance(config, dict) else None
    if raw in (None, ""):
        return DEFAULT_HEALTH_BELOW_THRESHOLD
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "AutoTicketRule %s has a non-numeric threshold %r; using %s.",
            getattr(rule, "pk", "?"), raw, DEFAULT_HEALTH_BELOW_THRESHOLD,
        )
        return DEFAULT_HEALTH_BELOW_THRESHOLD


def _evaluate_rule_health_below(rule, *, now) -> int:
    """Threshold rule: scan TenantHealthScore rows below `threshold` since last 24h."""

    try:
        from apps.customersuccess.models import TenantHealthScore
    except ImportError:
        return 0
    threshold = rule_threshold(rule)
    recent_since = now - timedelta(hours=24)
    qs = TenantHealthScore.objects.filter(  # tenant-isolation-allow: platform-operator-health-score-sweep-all-tenants
        score__lte=threshold, computed_at__gte=recent_since
    ).select_related("school")
    fired = 0
    for hs in qs:
        ok = _open_ticket(
            school=hs.school,
            title=f"Health score below {threshold} ({hs.score})",
            body=(
                f"Auto-ticket rule {rule.name!r} fired because tenant "
                f"{getattr(hs.school, 'slug', '?')} has a health score of {hs.score}.\n"
                f"Dimensions: {hs.dimensions or {}}"
            ),
            dedupe_key=f"auto_ticket:health_below:{rule.pk}:{hs.pk}",
        )
        if ok:
            fired += 1
    return fired


def evaluate_feedback_critical_rules(feedback) -> int:
    """Signal-driven: active FEEDBACK_CRITICAL rules for a new high/critical submission."""

    try:
        from apps.customersuccess.models import AutoTicketRule
        from apps.feedback.models import FeedbackSubmission
    except ImportError:
        return 0
    if feedback.severity not in (
        FeedbackSubmission.Severity.CRITICAL,
        FeedbackSubmission.Severity.HIGH,
    ):
        return 0
    if "auto_ticket" in (feedback.tags or []):
        return 0
    fired = 0
    for rule in AutoTicketRule.objects.filter(
        is_active=True,
        trigger=AutoTicketRule.Trigger.FEEDBACK_CRITICAL,
    ):
        ok = _open_ticket(
            school=feedback.school,
            title=f"Feedback {feedback.severity}: {(feedback.title or '')[:80]}",
            body=(
                f"Auto-ticket rule {rule.name!r} fired on feedback id={feedback.pk} "
                f"category={feedback.category} severity={feedback.severity}."
            ),
            source="auto_ticket_feedback_critical",
            dedupe_key=f"auto_ticket:feedback_critical:{rule.pk}:{feedback.pk}",
        )
        if ok:
            fired += 1
    return fired


def _evaluate_rule_risk_alert_red(rule, *, now) -> int:
    try:
        from apps.customersuccess.models import TenantRiskAlert
    except ImportError:
        return 0
    recent_since = now - timedelta(hours=24)
    qs = TenantRiskAlert.objects.filter(  # tenant-isolation-allow: platform-operator-risk-alert-sweep-all-tenants
        severity="red", created_at__gte=recent_since
    ).select_related("school")
    fired = 0
    for alert in qs:
        ok = _open_ticket(
            school=alert.school,
            title=f"RED risk alert: {alert.reason[:80] if hasattr(alert, 'reason') else 'unknown'}",
            body=f"Auto-ticket rule {rule.name!r} fired on red alert id={alert.pk}.",
            dedupe_key=f"auto_ticket:risk_alert_red:{rule.pk}:{alert.pk}",
        )
        if ok:
            fired += 1
    return fired


def run_all_rules() -> dict:
    """Evaluate every active AutoTicketRule. Returns counts per trigger.

    Each rule gets its OWN savepoint rather than sharing one outer atomic block.
    Under the old shape a single bad row -- a non-numeric threshold, a deleted
    school, anything -- raised through the whole pass, discarded the tickets
    earlier rules had legitimately opened, and was swallowed by the beat task's
    ``except Exception: return {}``. One malformed rule therefore disabled the
    entire engine every 10 minutes, forever, with a worker-log traceback as the
    only trace. A rule that fails now fails alone and is reported.
    """

    try:
        from apps.customersuccess.models import AutoTicketRule
    except ImportError:
        return {}
    now = timezone.now()
    counts: dict[str, int] = {}
    failures: dict[str, str] = {}
    for rule in AutoTicketRule.objects.filter(is_active=True):
        try:
            with transaction.atomic():
                if rule.trigger == AutoTicketRule.Trigger.HEALTH_BELOW:
                    counts[rule.name] = _evaluate_rule_health_below(rule, now=now)
                elif rule.trigger == AutoTicketRule.Trigger.RISK_ALERT_RED:
                    counts[rule.name] = _evaluate_rule_risk_alert_red(rule, now=now)
                # Other triggers (workflow_failure, inactivity_days) require
                # domain signals not implemented here yet.
        except Exception as exc:  # noqa: BLE001 -- one bad rule, not the pass
            counts[rule.name] = 0
            failures[rule.name] = type(exc).__name__
            logger.exception(
                "AutoTicketRule %s (%s) failed; other rules continue.",
                getattr(rule, "pk", "?"), rule.name,
            )
    if failures:
        counts["_failed_rules"] = failures
    return counts
