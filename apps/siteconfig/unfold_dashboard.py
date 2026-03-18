"""
Phase H: Unfold admin dashboard callback – Bento-style context and branding.

Admin (Configuration Engine) is superadmin-only and only mounted on the manager host.
We never inject tenant/school branding into admin: use platform (manager) branding only.
"""

# Platform/superadmin branding when admin is used (no tenant)
ADMIN_PLATFORM_PRIMARY = "#d4af37"
ADMIN_PLATFORM_ACCENT = "#0d6efd"


def dashboard_callback(request, context):
    """
    Called when the admin index is rendered. Add custom context for Bento-style dashboard.

    Admin is superadmin-only: do not use request.school or any tenant branding.
    Use platform branding so the Configuration Engine feels consistent with the manager.
    """
    path = (getattr(request, "path", "") or "").strip()
    if path.startswith("/admin/"):
        context["unfold_school_logo_url"] = ""
        context["unfold_school_primary_color"] = ADMIN_PLATFORM_PRIMARY
        context["unfold_school_accent_color"] = ADMIN_PLATFORM_ACCENT
        return context

    school = getattr(request, "school", None)
    if school:
        context["unfold_school_logo_url"] = getattr(school, "logo_url", None) or ""
        context["unfold_school_primary_color"] = (
            getattr(school, "primary_color", None) or "#0d6efd"
        )
        context["unfold_school_accent_color"] = (
            getattr(school, "accent_color", None) or "#198754"
        )
    else:
        context["unfold_school_logo_url"] = ""
        context["unfold_school_primary_color"] = "#0d6efd"
        context["unfold_school_accent_color"] = "#198754"
    return context
