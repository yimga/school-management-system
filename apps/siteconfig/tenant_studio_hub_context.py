"""Context builders for tenant School Studio hub (AI + coach, tenant-safe)."""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _


def _tenant_reverse(name: str) -> str:
    try:
        return reverse(name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(name)
        except NoReverseMatch:
            return ""


def build_studio_coach_message(
    *,
    progress: dict[str, Any],
    blockers: list[str],
) -> tuple[str, list[dict[str, str]]]:
    """Deterministic, actionable coach copy (no generic fluff)."""
    quick: list[dict[str, str]] = []
    na = progress.get("next_action") if isinstance(progress, dict) else None
    if isinstance(na, dict) and na.get("url"):
        quick.append(
            {
                "label": str(na.get("label") or _("Open next setup step"))[:120],
                "url": str(na["url"]),
            }
        )
    for row in (progress.get("steps") or [])[:6]:
        if not isinstance(row, dict) or row.get("done"):
            continue
        link = (row.get("link") or "").strip()
        if link:
            quick.append(
                {
                    "label": str(row.get("label") or _("Setup step"))[:120],
                    "url": link,
                }
            )
        if len(quick) >= 4:
            break

    parts: list[str] = []
    pct = int(progress.get("percent") or 0) if isinstance(progress, dict) else 0
    if blockers:
        parts.append(str(blockers[0]))
    if na and na.get("label"):
        parts.append(
            _("Focus next on “%(step)s” — use the primary action button or launch path.")
            % {"step": na["label"]}
        )
    elif pct < 50:
        parts.append(
            _(
                "Activation is below half complete. Open Activation checklist and finish "
                "academic year, staff, and students before go-live."
            )
        )
    else:
        parts.append(
            _(
                "Review readiness and launch checklist when health score is stable."
            )
        )
    return " ".join(parts).strip(), quick[:6]


def build_studio_ai_context(
    request: Any,
    *,
    school: Any,
    progress: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """AI panel: contextual tip + onboarding assistant binding."""
    from apps.platform_runtime.helpers import get_effective_flags
    from apps.siteconfig.ai_assistants import get_assistant

    flags = get_effective_flags(request)
    ai_enabled = bool(flags.get("enable_ai_center_help", True))
    assistant = get_assistant("onboarding_assistant") if ai_enabled else None
    api_url = ""
    if assistant and assistant.get("api_url_name"):
        try:
            api_url = reverse(assistant["api_url_name"])
        except NoReverseMatch:
            api_url = ""

    coach_message, quick_actions = build_studio_coach_message(
        progress=progress,
        blockers=blockers,
    )
    contextual: dict[str, Any] = {
        "tip": coach_message[:220],
        "ui_marker": "data-ai-contextual-insight",
        "module": "tenant_studio",
    }
    if ai_enabled and school is not None:
        try:
            from services.ai_center.contextual_insights import get_contextual_tip

            state = {}
            if blockers:
                state["blocker"] = str(blockers[0])[:120]
            if progress.get("next_action"):
                state["next_action"] = progress["next_action"]
            contextual = get_contextual_tip(
                request.user,
                school,
                _tenant_reverse("school_studio") or "/school/studio/",
                "tenant_studio",
                state,
            )
        except Exception:
            pass

    return {
        "ai_enabled": ai_enabled,
        "onboarding_assistant": assistant,
        "setup_assistant_api_url": api_url,
        "coach_message": coach_message,
        "coach_quick_actions": quick_actions,
        "contextual_tip": contextual,
        "onboarding_coach_url": _tenant_reverse("siteconfig:api_onboarding_coach"),
    }
