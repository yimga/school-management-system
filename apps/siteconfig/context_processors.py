from .models import SiteSettings

SESSION_KEY = "site_preview_settings"


def site_settings(request):
    """
    Provides SITE to all templates.
    If preview settings exist in session, use them (draft preview).
    Otherwise use DB singleton.
    """
    site = SiteSettings.get_solo()

    preview = request.session.get(SESSION_KEY)
    if preview:
        # overlay draft values on top of the DB object
        for key, value in preview.items():
            if hasattr(site, key):
                setattr(site, key, value)

        # handy flag for template UI
        setattr(site, "is_preview", True)
    else:
        setattr(site, "is_preview", False)

    return {
        "SITE": site,
        "SITE_THEME": site.active_theme,
        "REPORT_DOWNLOADS_ENABLED": site.report_downloads_enabled,
    }

