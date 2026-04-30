"""
Utility functions for user and account management.
"""

from django.contrib.auth import get_user_model

User = get_user_model()


def get_user_role(user) -> str:
    """
    Get normalized user role string.

    Args:
        user: User instance or None

    Returns:
        Uppercase role string, or empty string if no user/role
    """
    if not user:
        return ""
    return (getattr(user, "role", "") or "").upper()


def get_dashboard_context(user, page: str, request=None) -> dict:
    """
    Get standardized dashboard context for views.

    Args:
        user: User instance
        page: Dashboard page name (e.g., 'parent', 'teacher', 'backend')
        request: Optional HttpRequest — when provided, attaches ``platform_actions``
            from ``apps.platform_runtime.action_engine`` for template parity with
            the global context processor.

    Returns:
        Dictionary with dashboard settings, layout URL, widget metadata, etc.
    """
    from django.urls import reverse
    from django.utils.safestring import mark_safe
    import json
    from apps.runtime_blueprints.models import get_dashboard_widget_metadata
    from apps.siteconfig.dashboard_views import (
        load_dashboard_layout_settings,
        _can_customize,
        _can_light_customize,
    )

    can_customize = _can_customize(user)
    can_light_customize = _can_light_customize(user)
    effective_customize = can_customize or (
        str(page).strip().lower() == "parent" and can_light_customize
    )

    out = {
        "dashboard_settings": load_dashboard_layout_settings(user, page),
        "allow_custom_layout": effective_customize,
        "allow_light_customize": can_light_customize,
        "dashboard_layout_url": reverse("api:dashboard-layout", kwargs={"page": page}),
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
        "platform_actions": [],
        "platform_actions_json": mark_safe("[]"),
    }
    if request is not None:
        try:
            from apps.platform_runtime.action_engine import (
                get_actions_for_user,
                serialize_actions,
            )

            school = getattr(request, "school", None)
            from django.conf import settings as dj_settings

            lim = (
                1
                if getattr(dj_settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False)
                else 8
            )
            actions = get_actions_for_user(user, school, request=request, limit=lim)
            ser = serialize_actions(actions)
            out["platform_actions"] = ser
            out["platform_actions_json"] = mark_safe(json.dumps(ser))
        except Exception:  # noqa: BLE001
            pass
    return out
