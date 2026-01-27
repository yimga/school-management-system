import json
from django.db import DatabaseError, connection, transaction
from .models import SiteSettings, RegionConfig
from .translations import TranslationManager, SUPPORTED_LANGUAGES
from .models_dashboard import DashboardUserPreference
from django.core.files.storage import default_storage
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils import translation
from apps.accounts.models import User
from apps.finance.models import Notification
from .preview_state import PREVIEW_MODE_SESSION_KEY, ACT_AS_ROLE_SESSION_KEY

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


def _reset_db_state() -> None:
    """Reset a broken transaction after a handled DB error."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        else:
            connection.rollback()
    except Exception:
        pass


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


def _resolve_media_url(file_field, fallback: str | None = None) -> str:
    if not file_field:
        return static(fallback) if fallback else ""

    name = getattr(file_field, "name", "")
    if not name:
        return static(fallback) if fallback else ""

    try:
        if default_storage.exists(name):
            return file_field.url
    except Exception:
        pass

    return static(fallback) if fallback else ""


def site_settings(request):
    """
    Provides SITE to all templates.
    If preview settings exist in session, use them (draft preview).
    Otherwise use DB singleton.
    """
    if connection.needs_rollback:
        _reset_db_state()
    try:
        site = SiteSettings.get_solo()
    except DatabaseError:
        _reset_db_state()
        site = SiteSettings()

    preview_settings = request.session.get(SESSION_KEY)
    preview_mode_enabled = getattr(request, "preview_mode_enabled", False) or getattr(site, "preview_mode_enabled", False)
    preview_flag = bool(preview_settings) or preview_mode_enabled

    if preview_settings:
        for key, value in preview_settings.items():
            if hasattr(site, key):
                setattr(site, key, value)

    act_as_role = request.session.get(ACT_AS_ROLE_SESSION_KEY)
    act_as_choices = [{"value": code, "label": label} for code, label in User.Role.choices]
    setattr(site, "is_preview", preview_flag)

    breadcrumbs = _build_breadcrumbs(request.path)
    # Use theme pack backgrounds if set, else site settings
    logo_url = _resolve_media_url(site.get_theme_background("logo"), "images/logo.png")
    background_url = _resolve_media_url(site.get_theme_background("background_image"))

    try:
        portal_home_url = reverse("portal:home")
    except NoReverseMatch:
        portal_home_url = "/"

    # User preference override
    show_background_logo = True
    logo_opacity = site.get_theme_logo_opacity()
    high_contrast_mode = False
    reduced_motion = False
    theme_pref = "system"
    if request.user.is_authenticated:
        try:
            if hasattr(request.user, "preference"):
                pref = request.user.preference
                show_background_logo = pref.show_background_logo
                if pref.background_logo_opacity is not None:
                    logo_opacity = pref.background_logo_opacity
                high_contrast_mode = getattr(pref, "high_contrast_mode", False)
                reduced_motion = getattr(pref, "reduced_motion", False)
        except DatabaseError:
            _reset_db_state()
            pass
        try:
            dashboard_pref, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
            theme_pref = (dashboard_pref.theme_preference or "system").lower()
            high_contrast_mode = high_contrast_mode or bool(getattr(dashboard_pref, "high_contrast", False))
            reduced_motion = reduced_motion or bool(getattr(dashboard_pref, "reduced_motion", False))
        except DatabaseError:
            _reset_db_state()
            theme_pref = "system"

    video_bg_url = _resolve_media_url(site.get_theme_background("video_background"))
    svg_bg_url = _resolve_media_url(site.get_theme_background("svg_background"))
    try:
        finance_request_url = reverse("finance:requests")
    except NoReverseMatch:
        finance_request_url = "/finance/requests/"
    finance_request_alerts = 0
    if request.user.is_authenticated:
        finance_request_alerts = Notification.objects.filter(
            recipient=request.user,
            title__icontains="finance access request",
            is_read=False,
        ).count()
    admin_theme = site.get_admin_theme()
    admin_background_url = _resolve_media_url(admin_theme.background_image if admin_theme else None)
    admin_logo = _resolve_media_url(admin_theme.logo if admin_theme else None, "images/logo.png")
    return {
        "SITE": site,
        "SITE_SETTINGS": site,
        "SITE_THEME": site.active_theme,
        "SITE_ADMIN_THEME": admin_theme,
        "SITE_ADMIN_BACKGROUND_URL": admin_background_url,
        "SITE_ADMIN_LOGO_URL": admin_logo,
        "REPORT_DOWNLOADS_ENABLED": site.report_downloads_enabled,
        "BREADCRUMBS": breadcrumbs,
        "SITE_LOGO_URL": logo_url,
        "SITE_BACKGROUND_URL": background_url,
        "SITE_VIDEO_BG_URL": video_bg_url,
        "SITE_SVG_BG_URL": svg_bg_url,
        "SITE_LOGO_OPACITY": logo_opacity,
        "SHOW_BACKGROUND_LOGO": show_background_logo,
        "SITE_LOGO_BG_MODE": site.get_theme_logo_bg_mode(),
        "HIGH_CONTRAST_MODE": high_contrast_mode,
        "REDUCED_MOTION": reduced_motion,
        "USER_THEME_PREFERENCE": theme_pref,
        "portal_home_url": portal_home_url,
        "PREVIEW_ACT_AS_ROLE": act_as_role,
        "PREVIEW_ACT_AS_CHOICES": act_as_choices,
        "PREVIEW_NOTE": getattr(site, "preview_note", ""),
        "PREVIEW_MODE_ENABLED": preview_flag,
        "PREVIEW_TOGGLE_ENABLED": getattr(site, "preview_toggle_enabled", True),
        "PREVIEW_TOGGLE_LABEL": getattr(site, "preview_toggle_label", "Toggle preview"),
        "PREVIEW_BANNER_TEXT": getattr(site, "preview_banner_text", ""),
        "FINANCE_REQUEST_ALERT_COUNT": finance_request_alerts,
        "FINANCE_REQUEST_LINK": finance_request_url,
    }


def region_settings(request):
    """
    Provides region-specific settings and utilities to all templates.
    Phase 1.2.4: Internationalization & Multi-Region Support
    """
    from types import SimpleNamespace
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
    except DatabaseError:
        _reset_db_state()
        region = SimpleNamespace(
            code=getattr(settings, "REGION_CODE", "CMR"),
            name="Default",
            default_currency="XAF",
            date_format="YYYY-MM-DD",
            timezone=getattr(settings, "TIME_ZONE", "UTC"),
            default_language="en",
            grading_scale="default",
            decimal_separator=".",
            thousands_separator=",",
        )
    except DatabaseError:
        _reset_db_state()
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


def language_context(request):
    """
    Provide language-related context for templates.
    Supports region-based auto-selection and manual override.
    """
    # Determine current language
    current_language = translation.get_language()
    
    # Check for manual language preference
    if 'language' in request.GET:
        requested_language = request.GET.get('language')
        if requested_language in SUPPORTED_LANGUAGES:
            current_language = requested_language
            translation.activate(requested_language)
    elif 'django_language' in request.COOKIES:
        # Load from cookie
        cookie_language = request.COOKIES.get('django_language')
        if cookie_language in SUPPORTED_LANGUAGES:
            current_language = cookie_language
    else:
        # Try region-based auto-detection
        try:
            region = RegionConfig.get_default()
            if request.user and request.user.is_authenticated:
                # Check user region preference
                region_code = getattr(request.user, 'preferred_region', region.code)
                region = RegionConfig.objects.get(code=region_code)
            
            # Map region to language
            region_language_map = {
                'CMR': 'fr',  # Cameroon -> French
                'FRA': 'fr',  # France -> French
                'USA': 'en',  # USA -> English
                'GBR': 'en',  # UK -> English
                'KEN': 'sw',  # Kenya -> Swahili
                'NGA': 'yo',  # Nigeria -> Yoruba
                'DEU': 'en',  # Germany -> English (fallback)
            }
            
            default_language = region_language_map.get(region.code, 'en')
            if default_language in SUPPORTED_LANGUAGES:
                current_language = default_language
        except DatabaseError:
            _reset_db_state()
        except Exception:
            pass
    
    # Get available languages
    available_languages = [(code, name) for code, name in SUPPORTED_LANGUAGES.items()]
    current_language_name = SUPPORTED_LANGUAGES.get(current_language, 'English')
    
    return {
        'current_language': current_language,
        'current_language_name': current_language_name,
        'available_languages': available_languages,
        'supported_languages': SUPPORTED_LANGUAGES,
        'translate': lambda text: TranslationManager.get_text(text, current_language),
    }


def ai_copilot_settings(request):
    """
    Context processor for AI Copilot settings.
    Provides the Gemini API key and RBAC permissions to templates.
    
    Ensures AI copilot respects role-based access control:
    - ADMIN/LEADERSHIP: Full system access (analytics, finance, compliance)
    - TEACHER: Class and grade data access
    - PARENT: Child-specific data access
    - Other: General navigation only
    """
    import os
    
    # Get user role
    user_role = 'USER'
    if request.user and request.user.is_authenticated:
        user_role = (getattr(request.user, 'role', 'USER') or '').upper()
    
    admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "IT_ADMIN"}
    is_admin_like = request.user.is_superuser or request.user.is_staff or user_role in admin_roles

    # Determine AI permissions based on role
    ai_permissions = {
        'can_access_ai': request.user and request.user.is_authenticated,
        'can_analyze_data': False,
        'can_view_financial': False,
        'can_view_compliance': False,
        'can_access_grades': False,
        'can_access_roster': False,
        'scope': 'general',
    }
    
    if is_admin_like:
        ai_permissions.update({
            'can_analyze_data': True,
            'can_view_financial': True,
            'can_view_compliance': True,
            'can_access_grades': True,
            'can_access_roster': True,
            'scope': 'admin',
        })
    elif user_role == 'BURSAR':
        ai_permissions.update({
            'can_analyze_data': True,
            'can_view_financial': True,
            'scope': 'finance',
        })
    elif user_role == 'TEACHER':
        ai_permissions.update({
            'can_access_grades': True,
            'can_access_roster': True,
            'scope': 'teacher',
        })
    elif user_role == 'PARENT':
        ai_permissions.update({
            'can_access_grades': True,  # Only their child's
            'can_view_financial': True,  # Only their child's fees
            'scope': 'parent',
        })
    
    return {
        'GEMINI_API_KEY': os.environ.get('GEMINI_API_KEY', ''),
        'AI_PERMISSIONS': json.dumps(ai_permissions),
        'USER_ROLE': user_role,
    }
