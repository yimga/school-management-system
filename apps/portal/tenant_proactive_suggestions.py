"""
Proactive tenant suggestions for School Studio / onboarding (batch 1394).

Deterministic health + checklist signals — no LLM required for the nudge list.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

__all__ = ["proactive_suggestions_for_request"]


def proactive_suggestions_for_request(request) -> list[dict[str, Any]]:
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return []
    school = getattr(request, "school", None)
    if school is None:
        return []
    path = (getattr(request, "path", "") or "").lower()
    if not any(
        seg in path
        for seg in (
            "/school/studio",
            "/siteconfig/onboarding",
            "/authentication/backend/siteconfig/onboarding",
        )
    ):
        return []

    suggestions: list[dict[str, Any]] = []
    try:
        from apps.platform_runtime.onboarding import get_school_onboarding_progress
        from apps.platform_runtime.customer_health import calculate_school_health

        progress = get_school_onboarding_progress(school, user=request.user)
        health = calculate_school_health(school)
        pct = int(progress.get("percent") or 0)
        if pct < 50:
            suggestions.append(
                {
                    "severity": "warn",
                    "title": _("Finish activation essentials"),
                    "detail": _("Complete academic year, staff, and students before imports."),
                    "cta_label": _("Open checklist"),
                    "cta_url": _reverse_onboarding(request),
                }
            )
        status = (health.get("status") or "").strip()
        if status in ("setup_needed", "at_risk"):
            suggestions.append(
                {
                    "severity": "warn",
                    "title": _("Review school health"),
                    "detail": _("Health score suggests configuration or data gaps."),
                    "cta_label": _("School Studio"),
                    "cta_url": _reverse_studio(request),
                }
            )
        na = progress.get("next_action")
        if isinstance(na, dict) and na.get("url") and na.get("label"):
            suggestions.append(
                {
                    "severity": "info",
                    "title": str(na["label"])[:120],
                    "detail": _("Suggested next step from activation engine."),
                    "cta_label": _("Open"),
                    "cta_url": str(na["url"]),
                }
            )
    except Exception:
        return suggestions[:4]

    try:
        from django.conf import settings

        if not getattr(settings, "HELP_ZERO_RESULT_AUTO_DRAFT_KB", False):
            suggestions.append(
                {
                    "severity": "info",
                    "title": _("KB gap auto-draft"),
                    "detail": _(
                        "Enable HELP_ZERO_RESULT_AUTO_DRAFT_KB on the platform "
                        "to auto-queue KB drafts from zero-result searches."
                    ),
                    "cta_label": _("Help Center"),
                    "cta_url": _reverse_help(request),
                }
            )
    except Exception:
        pass

    try:
        from django.urls import reverse

        guide_url = reverse("portal:runmycampus_guide")
        if guide_url:
            suggestions.append(
                {
                    "severity": "info",
                    "title": _("RunMyCampus Guide"),
                    "detail": _(
                        "One directory for help, playbooks, and education packs."
                    ),
                    "cta_label": _("Open guide"),
                    "cta_url": guide_url,
                }
            )
    except Exception:
        pass

    return suggestions[:6]


def _reverse_onboarding(request) -> str:
    try:
        from django.urls import reverse

        return reverse("siteconfig:onboarding")
    except Exception:
        return ""


def _reverse_studio(request) -> str:
    try:
        from django.urls import reverse

        return reverse("school_studio", urlconf="config.tenant_urls")
    except Exception:
        return ""


def _reverse_help(request) -> str:
    try:
        from django.urls import reverse

        return reverse("feedback:help_center")
    except Exception:
        return ""
