"""
AI-assisted onboarding coach: one GET returns next-step copy + quick-action URLs for Setup Studio.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _build_rules_coach(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    health = payload.get("health_summary") or {}
    score = health.get("score")
    rn = payload.get("recommended_next") or {}
    quick: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def _add(label: str, url: str) -> None:
        if not url or url == "#" or url in seen_urls:
            return
        seen_urls.add(url)
        quick.append({"label": label[:120], "url": url})

    link = (rn.get("link") or "").strip()
    if link and link != "#":
        _add(
            str(rn.get("cta_label") or rn.get("label") or "Next step"),
            link,
        )
    for step in payload.get("steps") or []:
        if step.get("done"):
            continue
        sl = (step.get("link") or "").strip()
        if sl and sl != "#":
            _add(str(step.get("label") or "Open step"), sl)
        if len(quick) >= 6:
            break

    parts = []
    if score is not None:
        parts.append(f"Setup health is about {int(score)}%.")
    if rn:
        lab = rn.get("label") or "Continue setup"
        det = rn.get("detail") or rn.get("description") or rn.get("evidence") or ""
        parts.append(f"Focus next on: {lab}.")
        if det:
            parts.append(str(det)[:400])
    if not parts:
        parts.append(
            health.get("detail")
            or "Work through the checklist below — each link opens the right screen."
        )
    return " ".join(parts).strip(), quick[:6]


@login_required
@require_GET
def api_onboarding_coach(request):
    """
    Staff + tenant context: JSON with coach message, quick_actions, health_score.
    Optional AI_GATEWAY SETUP_RECOMMEND enriches coach_message when enabled.
    """
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "no_school"}, status=400)

    try:
        from apps.setup_studio.services import get_setup_studio_payload

        payload = get_setup_studio_payload(school)
    except Exception as e:  # noqa: BLE001 — API must not 500
        logger.debug("onboarding_coach payload failed: %s", e)
        return JsonResponse(
            {
                "ok": True,
                "coach_message": "Unable to load setup state. Refresh or open Studio Launch.",
                "quick_actions": [],
                "health_score": 0,
                "source": "error",
            }
        )

    coach_message, quick_actions = _build_rules_coach(payload)
    health = payload.get("health_summary") or {}
    score = health.get("score")
    if score is None:
        score = payload.get("setup_health_score") or 0
    source = "rules"

    if getattr(settings, "AI_GATEWAY_ENABLED", True):
        try:
            from services.ai_gateway import TaskType, invoke

            prompt = (
                "You are a concise school SaaS onboarding coach. No PII. "
                f"Health score ~{score}. Dominant task: {(payload.get('recommended_next') or {}).get('label', 'setup')}. "
                "Reply in 2–4 short sentences: what to do next and why. Plain text only."
            )
            text, meta = invoke(
                TaskType.SETUP_RECOMMEND,
                prompt,
                metadata={
                    "school_id": str(school.id),
                    "user_id": str(request.user.pk),
                },
            )
            if text and isinstance(text, str) and len(text.strip()) > 20:
                coach_message = text.strip()[:1200]
                source = "ai" if (meta.get("provider") or "") != "rules" else "rules+ai"
        except Exception as e:  # noqa: BLE001
            logger.debug("onboarding_coach AI optional: %s", e)

    return JsonResponse(
        {
            "ok": True,
            "coach_message": coach_message,
            "quick_actions": quick_actions,
            "health_score": int(score) if score is not None else 0,
            "launch_ready": bool(payload.get("launch_ready")),
            "source": source,
        }
    )
