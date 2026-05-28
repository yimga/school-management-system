"""
Launch Rail — merged onboarding path for self-serve and operator-created tenants.

Combines:
- Operator direction launch lanes (6)
- Setup Studio step definitions (weighted)
- Platform onboarding checklist (%)
- Fast path (4 steps to first_result)
"""

from __future__ import annotations

from typing import Any, Optional

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

FAST_PATH_STEPS: tuple[dict[str, Any], ...] = (
    {
        "key": "school_identity",
        "label": _("School identity"),
        "description": _("Confirm name, slug, region, and admin contact."),
        "url_name": "siteconfig:onboarding",
        "blocker_if": "missing_academic_year",
    },
    {
        "key": "academic_year",
        "label": _("Academic year"),
        "description": _("Add at least one academic year before roster import."),
        "url_name": "siteconfig:onboarding_step",
        "step_key": "academic_year",
        "blocker_if": "no_active_academic_year",
    },
    {
        "key": "roster_import",
        "label": _("Import roster"),
        "description": _("CSV import or Migration Cloud — minimum viable student set."),
        "url_name": "school_setup_imports",
    },
    {
        "key": "first_win",
        "label": _("First win"),
        "description": _("Invite an admin, record attendance, or post a fee."),
        "url_name": "activation_first_action",
    },
)


def _tenant_reverse(name: str, kwargs: Optional[dict] = None) -> str:
    try:
        return reverse(name, kwargs=kwargs or {}, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(name, kwargs=kwargs or {})
        except NoReverseMatch:
            return ""


def _fast_path_rows(school, user) -> list[dict[str, Any]]:
    from apps.platform_runtime.onboarding import get_school_onboarding_progress

    progress = get_school_onboarding_progress(school, user=user)
    done_keys = {s.get("key") for s in (progress.get("steps") or []) if s.get("done")}

    rows: list[dict[str, Any]] = []
    for step in FAST_PATH_STEPS:
        key = step["key"]
        url = ""
        if step.get("step_key"):
            url = _tenant_reverse(
                step["url_name"],
                kwargs={"step_key": step["step_key"]},
            )
        else:
            url = _tenant_reverse(step["url_name"])
        done = key in done_keys
        if key == "school_identity" and int(progress.get("percent") or 0) > 0:
            done = True
        if key == "academic_year":
            for s in progress.get("steps") or []:
                if s.get("key") == "academic_year" and s.get("done"):
                    done = True
        if key == "roster_import":
            for s in progress.get("steps") or []:
                if s.get("key") in ("students", "import_data") and s.get("done"):
                    done = True
        if key == "first_win":
            from apps.schools.models import MarketingFunnelEvent

            if MarketingFunnelEvent.objects.filter(
                school=school, event_type="first_result"
            ).exists():
                done = True
        rows.append(
            {
                "key": key,
                "label": str(step["label"]),
                "description": str(step["description"]),
                "url": url,
                "done": done,
                "required": True,
            }
        )
    return rows


def build_launch_rail_payload(school, user=None) -> dict[str, Any]:
    """Full launch rail for School Studio and provisioning status pages."""
    from apps.lifecycle.readiness import compute_unified_score
    from apps.lifecycle.unified_lifecycle import get_creation_path, resolve_unified_lifecycle
    from apps.platform_runtime.onboarding import get_school_onboarding_progress
    from apps.platform_runtime.tenant_onboarding_operator_direction import (
        launch_lanes_for_template,
    )
    from apps.setup_studio.services import get_setup_studio_payload

    unified = resolve_unified_lifecycle(school)
    readiness = compute_unified_score(school)
    progress = get_school_onboarding_progress(school, user=user)
    lanes = launch_lanes_for_template()
    fast_path = _fast_path_rows(school, user)
    fast_done = sum(1 for r in fast_path if r["done"])
    fast_pct = int(100 * fast_done / max(len(fast_path), 1))

    setup_payload: dict[str, Any] = {}
    try:
        setup_payload = get_setup_studio_payload(school) or {}
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        setup_payload = {}

    setup_steps = setup_payload.get("steps") or []
    path = get_creation_path(school)
    path_label = (
        str(_("Self-serve signup"))
        if path == "self_serve"
        else str(_("Operator provisioned"))
    )

    next_fast = next((r for r in fast_path if not r["done"]), None)

    return {
        "creation_path": path,
        "creation_path_label": path_label,
        "unified": unified,
        "readiness": readiness.to_dict(),
        "onboarding_percent": int(progress.get("percent") or 0),
        "launch_lanes": lanes,
        "fast_path": fast_path,
        "fast_path_percent": fast_pct,
        "fast_path_complete": fast_pct >= 100,
        "setup_studio_percent": int(setup_payload.get("progress_percent") or 0),
        "setup_steps": setup_steps[:12],
        "launch_ready": bool(readiness.launch_ready),
        "launch_blockers": list(readiness.launch_blockers or [])[:8],
        "next_action": {
            "label": (next_fast or {}).get("label") or progress.get("next_action", {}).get("label"),
            "url": (next_fast or {}).get("url") or (progress.get("next_action") or {}).get("url"),
        },
        "recommended_mode": "fast" if fast_pct < 100 else "full",
    }
