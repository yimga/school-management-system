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


def _open_ticket(*, school, title: str, body: str, source: str = "auto_ticket_rule") -> bool:
    """Create a FeedbackSubmission as the auto-ticket; safe across the
    edge cases where feedback isn't installed yet."""

    try:
        from apps.feedback.models import FeedbackSubmission
    except Exception:
        logger.warning("AutoTicketRule fired but feedback app not available.")
        return False
    try:
        FeedbackSubmission.objects.create(
            school=school,
            user=None,
            title=title[:180],
            description=body[:4000],
            category=FeedbackSubmission.Category.GENERAL,
            severity=FeedbackSubmission.Severity.HIGH,
            status=FeedbackSubmission.Status.NEW,
            privacy_level=FeedbackSubmission.PrivacyLevel.RMC_PRIVATE,
            tags=[source, "auto_ticket"],
        )
        return True
    except Exception as exc:
        logger.warning("AutoTicketRule could not write FeedbackSubmission: %s", exc)
        return False


def _evaluate_rule_health_below(rule, *, now) -> int:
    """Threshold rule: scan TenantHealthScore rows below `threshold` since last 24h."""

    try:
        from apps.customersuccess.models import TenantHealthScore
    except ImportError:
        return 0
    threshold = int(rule.config.get("threshold") or 50)
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
        )
        if ok:
            fired += 1
    return fired


@transaction.atomic
def run_all_rules() -> dict:
    """Evaluate every active AutoTicketRule. Returns counts per trigger."""

    try:
        from apps.customersuccess.models import AutoTicketRule
    except ImportError:
        return {}
    now = timezone.now()
    counts: dict[str, int] = {}
    for rule in AutoTicketRule.objects.filter(is_active=True):
        if rule.trigger == AutoTicketRule.Trigger.HEALTH_BELOW:
            counts[rule.name] = _evaluate_rule_health_below(rule, now=now)
        elif rule.trigger == AutoTicketRule.Trigger.RISK_ALERT_RED:
            counts[rule.name] = _evaluate_rule_risk_alert_red(rule, now=now)
        # Other triggers (workflow_failure, inactivity_days) require domain
        # signals not implemented here yet.
    return counts
