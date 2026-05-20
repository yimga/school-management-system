"""Global template context for help / feedback / product-voice surfaces."""

from __future__ import annotations

from django.urls import reverse


def support_links(request):
    """Expose host-aware help URLs in every authenticated shell."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        from apps.feedback.services import support_entry_points

        links = support_entry_points(request)
    except Exception:
        links = {}
    is_manager = getattr(request, "public_host_kind", None) == "manager"
    help_center_url = links.get("help_center") or ""
    if not help_center_url:
        try:
            help_center_url = reverse(
                "manager_help_center" if is_manager else "feedback:help_center"
            )
        except Exception:
            help_center_url = ""
    return {
        "support_links": links,
        "help_center_url": help_center_url,
        "feature_center_url": links.get("feature_center") or "",
        "contact_center_url": links.get("contact_center") or "",
    }
