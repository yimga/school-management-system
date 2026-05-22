"""
AI help governance — tenant feature flag + retention helpers (batch 1345).
"""

from __future__ import annotations


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


def is_parent_or_student_user(request) -> bool:
    """True when the authenticated user is a parent or student lane."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    role = (getattr(user, "role", "") or "").upper()
    return role in ("PARENT", "STUDENT")


def ai_assistant_panel_enabled_for_request(request) -> bool:
    """KB AI panel + floating copilot — respects tenant flag + parent/student policy."""
    if not ai_help_enabled_for_request(request):
        return False
    policy = parent_student_help_surface_policy()
    if is_parent_or_student_user(request) and not policy.get("ai_assistant_panel", False):
        return False
    return True


def should_redirect_feature_center_for_request(request) -> bool:
    """When True, parent/student feature-center visits should land on help center."""
    if not is_parent_or_student_user(request):
        return False
    return bool(parent_student_help_surface_policy().get("feature_center_redirect", False))


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
