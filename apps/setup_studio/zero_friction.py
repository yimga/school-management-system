"""
Setup Studio 50X zero-friction helpers — health, blockers, recommended setup, resume.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.remediation import RemediationPayload


def merge_persisted_wizard_state(
    progress_step_state: dict[str, Any] | None,
    launch_step_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Preserve ``step_state['wizards']`` when persisting launch-kernel steps."""
    merged: dict[str, Any] = dict(launch_step_state)
    if isinstance(progress_step_state, dict):
        wizards = progress_step_state.get("wizards")
        if isinstance(wizards, dict) and wizards:
            merged["wizards"] = wizards
    return merged


def get_zero_friction_payload(school) -> dict[str, Any]:
    from apps.setup_studio.models import SetupProgress
    from apps.setup_studio.services import get_setup_studio_payload
    from apps.setup_studio.wizard_extras import list_resumable_wizards

    payload = get_setup_studio_payload(school)
    progress = SetupProgress.objects.filter(school=school).first()
    wizards_ns = {}
    if progress and isinstance(progress.step_state, dict):
        wizards_ns = progress.step_state.get("wizards") or {}
    resumable = list_resumable_wizards(wizards_namespace=wizards_ns)
    blockers = list(payload.get("launch_blockers") or [])
    recommended = payload.get("recommended_next") or {}
    resume_url = ""
    if resumable:
        from django.urls import NoReverseMatch, reverse

        try:
            resume_url = reverse(
                "setup_studio:tenant_wizard",
                kwargs={"wizard_key": resumable[0].wizard_key},
            )
        except NoReverseMatch:
            resume_url = ""
    return {
        "health_score": payload.get("health_score", 0),
        "health_summary": payload.get("health_summary") or {},
        "launch_ready": bool(payload.get("launch_ready")),
        "launch_blockers": blockers,
        "recommended_next": recommended,
        "recommended_blueprint": payload.get("recommended_blueprint") or {},
        "resumable_wizards": resumable,
        "actions": {
            "use_recommended_setup": recommended.get("link") or "",
            "preview_setup": recommended.get("link") or "",
            "resume_wizard_url": resume_url,
            "what_is_blocking_launch": blockers,
        },
    }


def what_is_blocking_launch(school) -> dict[str, Any]:
    data = get_zero_friction_payload(school)
    blockers = data["launch_blockers"]
    explanations = [
        {
            "code": b.get("key") or b.get("step_key") or "blocker",
            "message": b.get("label") or b.get("message") or str(b),
            "cta_url": b.get("link") or b.get("cta_url") or "",
        }
        for b in blockers
    ]
    remediation = RemediationPayload(
        code="setup_studio.launch_blocked",
        message="Complete the remaining setup steps before launch."
        if blockers
        else "No blockers — you can launch.",
        human_action="Use recommended setup or resume your last wizard step."
        if blockers
        else "Review launch checklist and go live.",
        suggested_values={"blockers": explanations[:10]},
        auto_fix_available=bool(blockers),
        auto_fix_kind="auto_repair_setup" if blockers else "",
    )
    return {
        "blockers": explanations,
        "count": len(explanations),
        "launch_ready": data["launch_ready"],
        "remediation": remediation.to_tenant_api_dict(),
    }


def apply_recommended_setup(school, *, actor_id: int | None = None) -> dict[str, Any]:
    """
    Idempotent guidance packet for “Use recommended setup”.
    Does not mutate tenant data without explicit downstream wizard/launch actions.
    """
    data = get_zero_friction_payload(school)
    next_step = data.get("recommended_next") or {}
    blueprint = data.get("recommended_blueprint") or {}
    return {
        "ok": True,
        "actor_id": actor_id,
        "next_step_key": next_step.get("key", ""),
        "next_url": next_step.get("link") or "",
        # ``_rank_blueprints`` emits the pack slug under both ``slug`` and the
        # legacy ``pack_slug`` key; accept either so the recommended pack is not
        # silently dropped (the empty-slug bug on the launch surface).
        "recommended_blueprint_slug": (
            blueprint.get("slug")
            or blueprint.get("pack_slug")
            or blueprint.get("key")
            or ""
        ),
        "health_score": data["health_score"],
        "launch_ready": data["launch_ready"],
    }
