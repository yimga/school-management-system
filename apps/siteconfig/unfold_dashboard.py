"""
Phase H: Unfold admin dashboard callback – Bento-style context and per-tenant branding.
Injects school logo, primary/accent colors when request.school is set; optional KPIs for admin index.
"""


def dashboard_callback(request, context):
    """
    Called when the admin index is rendered. Add custom context for Bento-style dashboard
    and per-tenant branding (logo, colors) so the admin "feels" unique per school.
    """
    school = getattr(request, "school", None)
    if school:
        context["unfold_school_logo_url"] = getattr(school, "logo_url", None) or ""
        context["unfold_school_primary_color"] = getattr(school, "primary_color", None) or "#0d6efd"
        context["unfold_school_accent_color"] = getattr(school, "accent_color", None) or "#198754"
    else:
        context["unfold_school_logo_url"] = ""
        context["unfold_school_primary_color"] = "#0d6efd"
        context["unfold_school_accent_color"] = "#198754"
    return context
