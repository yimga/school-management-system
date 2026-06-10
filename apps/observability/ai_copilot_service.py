"""AI copilot service — operator rail insights (batch 1393).

Powers the *Pulse* insight feed of the manager ``cockpit.ai_copilot_rail`` when
enabled. Uses platform metrics and support backlog counts — no tenant PII in
suggestion copy.

HONESTY NOTE (do not mistake the module name for an inference engine): despite
the ``ai_copilot`` name, every function here is **deterministic and rules-based**
— it counts open tickets / pending AI reviews / KB gaps and reports whether the
real gateway is reachable. It makes **no model call**. The genuinely generative
side of the rail (the chat box) is served separately by the Studio OS copilot
rail (``apps.studio_os.copilot_rail_service`` via the ``studio_os:copilot_rail_*``
endpoints). The canonical generative-AI surface inventory lives in
``apps.platform_runtime.ai_providers.describe_ai_assistant_surfaces`` and is
surfaced in the Intelligence & Self-Healing hub; this feed is intentionally
**not** listed there because it is not AI.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

__all__ = [
    "build_copilot_suggestion_card",
    "build_copilot_activity_event",
    "enrich_manager_copilot_rail",
]


def build_copilot_suggestion_card(
    *,
    title: str = "",
    summary: str = "",
    cta_label: str = "",
    cta_action: str = "",
    severity: str = "info",
) -> dict[str, Any]:
    return {
        "title": title,
        "summary": summary,
        "cta_label": cta_label,
        "cta_action": cta_action,
        "severity": severity,
    }


def build_copilot_activity_event(
    *,
    icon: str = "•",
    text: str = "",
    time_label: str = "",
    severity: str = "info",
) -> dict[str, Any]:
    return {
        "icon": icon,
        "text": text,
        "time_label": time_label,
        "severity": severity,
    }


def _open_support_ticket_count() -> int | None:
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        open_statuses = (
            GlobalSupportTicket.Status.OPEN,
            GlobalSupportTicket.Status.IN_PROGRESS,
            GlobalSupportTicket.Status.WAITING,
        )
        return GlobalSupportTicket.objects.filter(status__in=open_statuses).count()  # tenant-isolation-allow: global-support-ticket-platform-wide-aggregate-for-operator-copilot
    except Exception:
        logger.debug("copilot open ticket count skipped", exc_info=True)
        return None


def _pending_ai_review_count() -> int | None:
    try:
        from apps.feedback.models import SupportAIInteractionReview

        return SupportAIInteractionReview.objects.filter(  # tenant-isolation-allow: ai-review-queue-platform-wide-aggregate-for-operator-copilot
            status=SupportAIInteractionReview.Status.PENDING
        ).count()
    except Exception:
        logger.debug("copilot ai review count skipped", exc_info=True)
        return None


def _content_gap_backlog_count() -> int | None:
    try:
        from apps.feedback.models import HelpContentGapTask

        return HelpContentGapTask.objects.filter(
            status__in=(
                HelpContentGapTask.Status.OPEN,
                HelpContentGapTask.Status.ASSIGNED,
            )
        ).count()
    except Exception:
        logger.debug("copilot gap backlog skipped", exc_info=True)
        return None


def enrich_manager_copilot_rail(request: Any | None = None) -> dict[str, Any]:
    """Live operator insights overlay for cockpit.ai_copilot_rail."""
    suggestions: list[dict[str, Any]] = []
    activity: list[dict[str, Any]] = []

    open_tickets = _open_support_ticket_count()
    if open_tickets is not None and open_tickets > 0:
        suggestions.append(
            build_copilot_suggestion_card(
                title=_("Support queue"),
                summary=_("%(count)s open platform tickets need triage.")
                % {"count": open_tickets},
                cta_label=_("Open support"),
                cta_action="navigate:/help-center/",
                severity="warn" if open_tickets > 5 else "info",
            )
        )

    ai_pending = _pending_ai_review_count()
    if ai_pending is not None and ai_pending > 0:
        suggestions.append(
            build_copilot_suggestion_card(
                title=_("AI review queue"),
                summary=_("%(count)s failed support AI interactions await HITL.")
                % {"count": ai_pending},
                cta_label=_("Review AI"),
                cta_action="navigate:/help-center/ai-review/",
                severity="warn",
            )
        )

    gaps = _content_gap_backlog_count()
    if gaps is not None and gaps > 0:
        suggestions.append(
            build_copilot_suggestion_card(
                title=_("KB content gaps"),
                summary=_("%(count)s zero-result search clusters need articles.")
                % {"count": gaps},
                cta_label=_("Help analytics"),
                cta_action="navigate:/help-center/",
                severity="info",
            )
        )

    try:
        from services.ai_helpers import is_ai_available

        ai_on = is_ai_available(None)
    except Exception:
        ai_on = False
    insight_text = (
        _("Cloud AI gateway is reachable — copilot can draft KB and support.")
        if ai_on
        else _("Rules fallback active — enable LiteLLM on Render for generative help.")
    )

    if request is not None:
        path = (getattr(request, "path", None) or "")[:120]
        if path:
            activity.append(
                build_copilot_activity_event(
                    icon="◎",
                    text=_("Active screen: %(path)s") % {"path": path},
                    time_label=_("now"),
                    severity="info",
                )
            )

    return {
        "enabled": True,
        "intro_text": _("RunMyCampus Guide"),
        "insight_text": insight_text,
        "insight_em": "",
        "suggested_actions": [s.get("title", "") for s in suggestions[:4] if s.get("title")],
        "suggestions": suggestions[:6],
        "activity": activity[:4],
        "shortcut_hint": _("Cmd/Ctrl + K"),
        "empty_state_text": _("No urgent operator actions — explore Help Center analytics."),
        "deferred_marker": "",
    }


