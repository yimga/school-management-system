"""
AI help governance — tenant feature flag + retention helpers (batch 1345).
"""

from __future__ import annotations

from typing import Any


def ai_help_enabled_for_request(request) -> bool:
    """7-layer cascade: SiteSettings backend_feature_flags.enable_ai_help_assistant."""
    try:
        school = getattr(request, "school", None)
        if school is not None:
            settings = getattr(school, "settings", None) or {}
            if isinstance(settings, dict):
                flags = settings.get("backend_feature_flags") or {}
                if "enable_ai_help_assistant" in flags:
                    return bool(flags.get("enable_ai_help_assistant"))
        from apps.siteconfig.models import SiteSettings

        flags = SiteSettings.get_solo().get_backend_feature_flags()
        return bool(flags.get("enable_ai_help_assistant", True))
    except Exception:
        return True


def parent_student_help_surface_policy() -> dict[str, bool]:
    """
    Parent/student lanes: reduced AI/deflection by design (batch 1354).

    Returns flags consumed by templates/docs — not a hard block on KB browse.
    """
    return {
        "ai_assistant_panel": False,
        "support_deflection_on_submit": True,
        "feature_center_redirect": True,
    }


def help_telemetry_retention_days() -> int:
    try:
        from apps.siteconfig.models import SiteSettings

        flags = SiteSettings.get_solo().get_backend_feature_flags()
        raw = flags.get("help_telemetry_retention_days", 365)
        return max(30, int(raw))
    except Exception:
        return 365
