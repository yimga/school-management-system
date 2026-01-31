# -*- coding: utf-8 -*-
"""
Feature Control Panel - toggle modules and features at runtime.
Access: superuser only.
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.siteconfig.models import (
    SiteSettings,
    default_portal_features,
    default_backend_feature_flags,
)


# Categories and their toggles (field/key -> label, critical=False)
FEATURE_CATEGORIES = {
    "academic": [
        ("portal_features.syllabus", "Class Syllabus", False),
    ],
    "administrative": [
        ("enable_parent_portal", "Parent Portal", True),
        ("enable_teacher_portal", "Teacher Portal", True),
        ("enable_reports_pdf", "Report Card PDFs", False),
        ("report_downloads_enabled", "Report Downloads", False),
    ],
    "support": [
        ("portal_features.documents", "Document Library", False),
        ("portal_features.forums", "Community Forums", False),
        ("portal_features.video", "Video Hub", False),
        ("portal_features.messaging", "Messaging", False),
    ],
    "backend": [
        ("backend_flags.enable_entity_console", "Entity Console", False),
        ("backend_flags.enable_entity_import", "Entity Import", False),
        ("backend_flags.enable_api_schema_ui", "API Schema UI", False),
    ],
}


def _get_site_features(site: SiteSettings) -> dict:
    """Return current feature state for display and form."""
    portal = site.portal_features or default_portal_features()
    flags = site.backend_feature_flags or default_backend_feature_flags()
    return {
        "enable_parent_portal": site.enable_parent_portal,
        "enable_teacher_portal": site.enable_teacher_portal,
        "enable_reports_pdf": site.enable_reports_pdf,
        "report_downloads_enabled": site.report_downloads_enabled,
        "portal_features.documents": bool(portal.get("documents")),
        "portal_features.forums": bool(portal.get("forums")),
        "portal_features.video": bool(portal.get("video")),
        "portal_features.messaging": bool(portal.get("messaging")),
        "portal_features.syllabus": bool(portal.get("syllabus")),
        "backend_flags.enable_entity_console": bool(flags.get("enable_entity_console")),
        "backend_flags.enable_entity_import": bool(flags.get("enable_entity_import")),
        "backend_flags.enable_api_schema_ui": bool(flags.get("enable_api_schema_ui")),
    }


def _apply_form_to_site(site: SiteSettings, form_data: dict) -> None:
    """Apply form checkbox values to SiteSettings."""
    portal = dict(site.portal_features or default_portal_features())
    flags = dict(site.backend_feature_flags or default_backend_feature_flags())

    for key, val in form_data.items():
        if key.startswith("portal_features."):
            subkey = key.split(".", 1)[1]
            portal[subkey] = bool(val)
        elif key.startswith("backend_flags."):
            subkey = key.split(".", 1)[1]
            flags[subkey] = bool(val)
        elif key == "enable_parent_portal":
            site.enable_parent_portal = bool(val)
        elif key == "enable_teacher_portal":
            site.enable_teacher_portal = bool(val)
        elif key == "enable_reports_pdf":
            site.enable_reports_pdf = bool(val)
        elif key == "report_downloads_enabled":
            site.report_downloads_enabled = bool(val)

    site.portal_features = portal
    site.backend_feature_flags = flags
    site.save(update_fields=[
        "enable_parent_portal", "enable_teacher_portal",
        "enable_reports_pdf", "report_downloads_enabled",
        "portal_features", "backend_feature_flags", "updated_at",
    ])


@require_http_methods(["GET", "POST"])
def feature_control_panel(request):
    """Feature Control Panel - toggle modules system-wide. Superuser only."""
    if not getattr(request.user, "is_authenticated", False):
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if not getattr(request.user, "is_superuser", False):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only superusers can access the Feature Control Panel.")
    site = SiteSettings.get_solo()
    current = _get_site_features(site)

    if request.method == "POST":
        form_data = {}
        for key in current:
            form_data[key] = request.POST.get(f"feature_{key}") == "on"
        _apply_form_to_site(site, form_data)
        messages.success(request, "Feature settings saved. Changes take effect immediately.")
        return redirect("siteconfig:feature_control_panel")

    # Build rows for template
    categories = []
    cat_labels = {
        "academic": ("Academic", "bi-journal-text"),
        "administrative": ("Administrative", "bi-gear"),
        "support": ("Support & Communication", "bi-chat-dots"),
        "backend": ("Backend Tools", "bi-tools"),
    }
    active_count = 0
    for cat_id, rows in FEATURE_CATEGORIES.items():
        label, icon = cat_labels.get(cat_id, (cat_id.title(), "bi-circle"))
        items = []
        for key, lbl, critical in rows:
            val = current.get(key, False)
            if val:
                active_count += 1
            items.append({
                "key": key,
                "label": lbl,
                "enabled": val,
                "critical": critical,
            })
        categories.append({"id": cat_id, "label": label, "icon": icon, "items": items})

    total = sum(len(c["items"]) for c in categories)
    return render(request, "siteconfig/feature_control_panel.html", {
        "categories": categories,
        "active_count": active_count,
        "total_count": total,
        "site_settings_id": site.pk,
    })
