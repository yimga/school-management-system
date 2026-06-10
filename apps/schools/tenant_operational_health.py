"""
Per-tenant operational health for school dashboards (admin, teacher, parent).

Combines platform fleet signals with tenant-scoped operational metrics so
dashboard widgets can show up / degraded / down in real time.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.db import DatabaseError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

TENANT_HEALTH_POLL_SECONDS = 15
TIER_UP = "up"
TIER_DEGRADED = "degraded"
TIER_DOWN = "down"


def _tier_rank(tier: str) -> int:
    if tier == TIER_DOWN:
        return 2
    if tier == TIER_DEGRADED:
        return 1
    return 0


def _merge_tier(current: str, candidate: str) -> str:
    return candidate if _tier_rank(candidate) > _tier_rank(current) else current


def _tenant_ops_metrics(request) -> dict[str, int]:
    metrics = {
        "overdue_invoices": 0,
        "draft_invoices": 0,
        "unpublished_terms": 0,
        "reminders_due": 0,
        "pending_access_requests": 0,
    }
    try:
        from apps.finance.models import Invoice, PaymentReminder
        from apps.reports.models import TermPublishStatus

        metrics["overdue_invoices"] = Invoice.objects.filter(
            status=Invoice.Status.OVERDUE
        ).count()
        metrics["draft_invoices"] = Invoice.objects.filter(
            status=Invoice.Status.DRAFT
        ).count()
        metrics["unpublished_terms"] = TermPublishStatus.objects.filter(
            is_published=False
        ).count()
        metrics["reminders_due"] = PaymentReminder.objects.filter(
            is_active=True,
            next_send_at__lte=timezone.now(),
        ).count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("tenant_operational_health: finance metrics unavailable", exc_info=True)

    try:
        from apps.requests.models import AccessRequest

        metrics["pending_access_requests"] = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        pass

    return metrics


def _parent_portal_metrics(request) -> dict[str, int]:
    metrics = {
        "linked_children": 0,
        "finance_overdue": 0,
        "fees_due": 0,
    }
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return metrics

    try:
        from apps.portal.services import guardian_student_links

        links = guardian_student_links(user)
        metrics["linked_children"] = links.count()
        finance_links = guardian_student_links(user, finance_only=True)
        finance_students = [link.student_id for link in finance_links if link.student_id]
        if finance_students:
            from apps.finance.models import Invoice

            overdue_qs = Invoice.objects.filter(
                student_id__in=finance_students,
                status=Invoice.Status.OVERDUE,
            )
            metrics["finance_overdue"] = overdue_qs.count()
            open_qs = Invoice.objects.filter(
                student_id__in=finance_students,
                status__in=(
                    Invoice.Status.ISSUED,
                    Invoice.Status.PARTIAL,
                    Invoice.Status.OVERDUE,
                ),
            )
            metrics["fees_due"] = open_qs.count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("tenant_operational_health: parent metrics unavailable", exc_info=True)

    return metrics


def _student_portal_metrics(request) -> dict[str, int]:
    metrics = {
        "profile_linked": 0,
        "unread_messages": 0,
    }
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return metrics

    try:
        from apps.communication.models import Message
        from apps.people.models import StudentProfile

        metrics["profile_linked"] = int(
            StudentProfile.objects.filter(user=user, is_active=True).exists()
        )
        metrics["unread_messages"] = Message.objects.filter(
            recipient=user,
            is_read=False,
        ).count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("tenant_operational_health: student metrics unavailable", exc_info=True)

    return metrics


def resolve_tenant_operational_health(
    school,
    *,
    request=None,
    surface: str = "admin",
) -> dict[str, Any]:
    """Return ``{tier, label, signals, revision, poll_interval_seconds}``."""
    signals: list[dict[str, str]] = []
    tier = TIER_UP
    label = str(_("All systems operational"))

    if school is None:
        return {
            "tier": TIER_DOWN,
            "label": str(_("No school context")),
            "signals": [{"key": "context", "label": str(_("School not bound")), "tone": "danger"}],
            "revision": "none",
            "poll_interval_seconds": TENANT_HEALTH_POLL_SECONDS,
            "generated_at": timezone.now().isoformat(),
        }

    from apps.schools.fleet_status import resolve_school_fleet_status

    fleet = resolve_school_fleet_status(school)
    heatmap = fleet.get("heatmap_tier") or "warn"
    fleet_label = fleet.get("fleet_state_label") or ""

    if heatmap == "danger" or not fleet.get("is_active"):
        tier = TIER_DOWN
        label = fleet_label or str(_("Service interrupted"))
        signals.append(
            {
                "key": "platform",
                "label": fleet_label or str(_("Platform restriction")),
                "tone": "danger",
            }
        )
    elif heatmap == "warn":
        tier = TIER_DEGRADED
        label = fleet_label or str(_("Needs attention"))
        signals.append(
            {
                "key": "platform",
                "label": fleet_label or str(_("Provisioning or approval pending")),
                "tone": "warning",
            }
        )
    elif heatmap == "idle":
        tier = TIER_DOWN
        label = str(_("Inactive"))
        signals.append(
            {"key": "platform", "label": str(_("School is inactive")), "tone": "muted"}
        )

    if request is not None and surface in ("admin", "backend"):
        metrics = _tenant_ops_metrics(request)
        if metrics["overdue_invoices"] > 0:
            tier = _merge_tier(tier, TIER_DEGRADED)
            if tier == TIER_UP:
                label = str(_("Finance attention needed"))
            signals.append(
                {
                    "key": "finance_overdue",
                    "label": _("{n} overdue invoices").format(n=metrics["overdue_invoices"]),
                    "tone": "warning",
                }
            )
        if metrics["unpublished_terms"] > 0:
            tier = _merge_tier(tier, TIER_DEGRADED)
            signals.append(
                {
                    "key": "terms",
                    "label": _("{n} unpublished terms").format(n=metrics["unpublished_terms"]),
                    "tone": "warning",
                }
            )
        if metrics["reminders_due"] > 0:
            signals.append(
                {
                    "key": "reminders",
                    "label": _("{n} payment reminders due").format(n=metrics["reminders_due"]),
                    "tone": "warning",
                }
            )
        if metrics["pending_access_requests"] > 0:
            signals.append(
                {
                    "key": "access_requests",
                    "label": _("{n} pending access requests").format(
                        n=metrics["pending_access_requests"]
                    ),
                    "tone": "info",
                }
            )

    if surface in ("teacher", "parent", "student"):
        try:
            from apps.siteconfig.config_service import get_effective_site_settings

            site = get_effective_site_settings(request=request) if request else None
            if surface == "parent" and site and not getattr(site, "enable_parent_portal", True):
                tier = _merge_tier(tier, TIER_DEGRADED)
                signals.append(
                    {
                        "key": "parent_portal",
                        "label": str(_("Parent portal is disabled")),
                        "tone": "warning",
                    }
                )
            if surface == "teacher" and site and not getattr(site, "enable_teacher_portal", True):
                tier = _merge_tier(tier, TIER_DEGRADED)
                signals.append(
                    {
                        "key": "teacher_portal",
                        "label": str(_("Teacher portal is disabled")),
                        "tone": "warning",
                    }
                )
            if surface == "student" and site and not getattr(site, "enable_student_portal", True):
                tier = _merge_tier(tier, TIER_DEGRADED)
                signals.append(
                    {
                        "key": "student_portal",
                        "label": str(_("Student portal is disabled")),
                        "tone": "warning",
                    }
                )
        except (AttributeError, DatabaseError, TypeError, ValueError):
            pass

    if request is not None and surface == "student":
        student_metrics = _student_portal_metrics(request)
        if not student_metrics["profile_linked"]:
            tier = _merge_tier(tier, TIER_DEGRADED)
            if tier == TIER_UP:
                label = str(_("Profile setup needed"))
            signals.append(
                {
                    "key": "student_profile",
                    "label": str(_("Student profile not linked")),
                    "tone": "warning",
                }
            )
        if student_metrics["unread_messages"] > 0:
            signals.append(
                {
                    "key": "student_messages",
                    "label": _("{n} unread messages").format(n=student_metrics["unread_messages"]),
                    "tone": "info",
                }
            )

    if request is not None and surface == "parent":
        parent_metrics = _parent_portal_metrics(request)
        if parent_metrics["linked_children"] == 0:
            tier = _merge_tier(tier, TIER_DEGRADED)
            if tier == TIER_UP:
                label = str(_("Link a child to get started"))
            signals.append(
                {
                    "key": "link_child",
                    "label": str(_("No linked children")),
                    "tone": "warning",
                }
            )
        if parent_metrics["finance_overdue"] > 0:
            tier = _merge_tier(tier, TIER_DEGRADED)
            if tier == TIER_UP:
                label = str(_("Fees need attention"))
            signals.append(
                {
                    "key": "parent_finance_overdue",
                    "label": _("{n} overdue invoices").format(n=parent_metrics["finance_overdue"]),
                    "tone": "warning",
                }
            )
        elif parent_metrics["fees_due"] > 0:
            signals.append(
                {
                    "key": "parent_fees_due",
                    "label": _("{n} open invoices").format(n=parent_metrics["fees_due"]),
                    "tone": "info",
                }
            )

    if not signals and tier == TIER_UP:
        signals.append(
            {"key": "ok", "label": str(_("No blockers detected")), "tone": "success"}
        )

    fingerprint = {
        "tier": tier,
        "label": label,
        "fleet_state": fleet.get("fleet_state"),
        "signals": signals,
    }
    revision = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "tier": tier,
        "label": label,
        "signals": signals,
        "revision": revision,
        "poll_interval_seconds": TENANT_HEALTH_POLL_SECONDS,
        "generated_at": timezone.now().isoformat(),
        "school_slug": getattr(school, "slug", "") or "",
    }
