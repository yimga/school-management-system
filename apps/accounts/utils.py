"""
Utility functions for user and account management.
"""
from typing import Optional
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


def get_dashboard_context(user, page: str) -> dict:
    """
    Get standardized dashboard context for views.
    
    Args:
        user: User instance
        page: Dashboard page name (e.g., 'parent', 'teacher', 'backend')
        
    Returns:
        Dictionary with dashboard settings, layout URL, widget metadata, etc.
    """
    from django.urls import reverse
    from django.utils.safestring import mark_safe
    import json
    from apps.siteconfig.dashboard_views import load_dashboard_layout_settings, _can_customize
    from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
    
    return {
        "dashboard_settings": load_dashboard_layout_settings(user, page),
        "allow_custom_layout": _can_customize(user),
        "dashboard_layout_url": reverse("api:dashboard-layout", kwargs={"page": page}),
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
    }
