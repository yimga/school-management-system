from .models import SiteSettings

SESSION_KEY = "site_preview_settings"

BREADCRUMB_LABELS = {
    "admissions": "Admissions",
    "application-status": "Application Status",
    "student-portal": "Student Portal",
    "grades": "Grades",
    "parent": "Parent Portal",
    "portal": "Portal",
    "finance": "Finance",
    "payments": "Payments",
    "receipts": "Receipts",
    "payroll": "Payroll",
    "reports": "Reports",
    "siteconfig": "Site Settings",
    "customizer": "Customizer",
    "preferences": "Preferences",
    "reports": "Reports",
    "reports/download": "Download",
    "analytics": "Analytics",
}


def _build_breadcrumbs(request_path: str) -> list[dict[str, str]]:
    segments = [
        segment
        for segment in request_path.strip("/").split("/")
        if segment and segment not in {"static", "media", "favicon.ico"}
    ]

    breadcrumbs = [{"label": "Home", "url": "/"}]
    if not segments:
        return breadcrumbs

    prefix = ""
    for index, segment in enumerate(segments, start=1):
        prefix += f"/{segment}"
        label = BREADCRUMB_LABELS.get(segment, segment.replace("_", " ").replace("-", " ").title())

        breadcrumbs.append(
            {
                "label": label,
                "url": prefix,
                "active": index == len(segments),
            }
        )

    return breadcrumbs


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

    breadcrumbs = _build_breadcrumbs(request.path)

    return {
        "SITE": site,
        "SITE_SETTINGS": site,
        "SITE_THEME": site.active_theme,
        "REPORT_DOWNLOADS_ENABLED": site.report_downloads_enabled,
        "BREADCRUMBS": breadcrumbs,
    }


def region_settings(request):
    """
    Provides region-specific settings and utilities to all templates.
    Phase 1.2.4: Internationalization & Multi-Region Support
    """
    from django.conf import settings
    from .models import RegionConfig
    from apps.evals.grading import CURRENCY_SYMBOLS
    
    try:
        # Try to get region from user preferences, session, or use default
        region_code = getattr(request.user, 'profile', {}).get('region', None) if request.user.is_authenticated else None
        region_code = region_code or request.session.get('region_code', settings.REGION_CODE)
        
        region = RegionConfig.objects.get(code=region_code)
    except RegionConfig.DoesNotExist:
        # Fallback to default region (Cameroon)
        region = RegionConfig.get_default()
    
    currency_symbol = CURRENCY_SYMBOLS.get(region.default_currency, region.default_currency)
    
    return {
        'region': region,
        'region_code': region.code,
        'region_name': region.name,
        'currency_symbol': currency_symbol,
        'date_format': region.date_format,
        'timezone': region.timezone,
        'default_language': region.default_language,
        'grading_scale': region.grading_scale,
        'decimal_separator': region.decimal_separator,
        'thousands_separator': region.thousands_separator,
    }


