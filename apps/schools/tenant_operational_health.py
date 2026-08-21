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


def _tenant_ops_metrics(school) -> dict[str, int]:
    metrics = {
        "overdue_invoices": 0,
        "draft_invoices": 0,
        "unpublished_terms": 0,
        "reminders_due": 0,
        "pending_access_requests": 0,
    }
    if school is None:
        return metrics
    try:
        from apps.finance.models import Invoice, PaymentReminder
        from apps.reports.models import TermPublishStatus

        metrics["overdue_invoices"] = Invoice.objects.filter(
            school=school,
            status=Invoice.Status.OVERDUE,
        ).count()
        metrics["draft_invoices"] = Invoice.objects.filter(
            school=school,
            status=Invoice.Status.DRAFT,
        ).count()
        metrics["unpublished_terms"] = TermPublishStatus.objects.filter(
            academic_year__school=school,
            is_published=False,
        ).count()
        metrics["reminders_due"] = PaymentReminder.objects.filter(
            invoice__school=school,
            is_active=True,
            next_send_at__lte=timezone.now(),
        ).count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        logger.debug("tenant_operational_health: finance metrics unavailable", exc_info=True)

    try:
        from apps.requests.models import AccessRequest

        metrics["pending_access_requests"] = AccessRequest.objects.filter(
            school=school,
            status=AccessRequest.Status.PENDING,
        ).count()
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        pass

    return metrics


def _parent_portal_metrics(request, school) -> dict[str, int]:
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
        if finance_students and school is not None:
            from apps.finance.models import Invoice

            overdue_qs = Invoice.objects.filter(
                school=school,
                student_id__in=finance_students,
                status=Invoice.Status.OVERDUE,
            )
            metrics["finance_overdue"] = overdue_qs.count()
            open_qs = Invoice.objects.filter(
                school=school,
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


def _student_portal_metrics(request, school) -> dict[str, int]:
    metrics = {
        "profile_linked": 0,
        "unread_messages": 0,
    }
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False) or school is None:
        return metrics

    try:
        from apps.communication.models import Message
        from apps.people.models import StudentProfile

        metrics["profile_linked"] = int(
            StudentProfile.objects.filter(
                user=user,
                school=school,
                is_active=True,
            ).exists()
        )
        metrics["unread_messages"] = Message.objects.filter(
            recipient=user,
            school=school,
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
        metrics = _tenant_ops_metrics(school)
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
            from apps.platform_runtime.config_resolver import get_effective_config

            if surface == "parent" and request and not get_effective_config(
                key="enable_parent_portal", request=request, default=True
            ):
                tier = _merge_tier(tier, TIER_DEGRADED)
                signals.append(
                    {
                        "key": "parent_portal",
                        "label": str(_("Parent portal is disabled")),
                        "tone": "warning",
                    }
                )
            if surface == "teacher" and request and not get_effective_config(
                key="enable_teacher_portal", request=request, default=True
            ):
                tier = _merge_tier(tier, TIER_DEGRADED)
                signals.append(
                    {
                        "key": "teacher_portal",
                        "label": str(_("Teacher portal is disabled")),
                        "tone": "warning",
                    }
                )
            if surface == "student" and request and not get_effective_config(
                key="enable_student_portal", request=request, default=True
            ):
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
        student_metrics = _student_portal_metrics(request, school)
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
        parent_metrics = _parent_portal_metrics(request, school)
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

    if surface == "admin":
        # Integration delivery. A school can attach its own mail server, have the
        # form accept it, and never send anything — the backend CLASS is global
        # while host/credentials are per-school, so a preview backend silently
        # discards a perfectly good configuration. Nothing errors, so the only way
        # an admin ever learns is if we tell them.
        #
        # Informational by decision: this degrades the tier so it is visible, and
        # never blocks. A school that has deliberately chosen no email raises
        # nothing at all (delivery_problems returns only real problems).
        try:
            from apps.schools.integration_delivery import delivery_problems

            for status in delivery_problems(school):
                tier = _merge_tier(tier, TIER_DEGRADED)
                if status.config_ignored and status.blocked:
                    text = _("{name} not sending — {n} waiting").format(
                        name=status.name, n=status.blocked,
                    )
                elif status.config_ignored:
                    text = _("{name} settings are not in use").format(name=status.name)
                else:
                    text = _("{name}: {n} waiting to send").format(
                        name=status.name, n=status.blocked,
                    )
                signals.append(
                    {
                        "key": f"delivery_{status.key}",
                        "label": str(text),
                        "tone": "warning",
                        # Carried for richer surfaces + the JSON API; the chip
                        # template reads only label + tone, so this is additive.
                        "detail": str(status.reason or ""),
                        "remedy": str(status.remedy or ""),
                    }
                )
        except Exception:  # noqa: BLE001 — a health probe must never break the dashboard
            logger.debug("tenant health: delivery probes unavailable", exc_info=True)

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
