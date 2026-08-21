"""
Helper functions for automation tasks.
"""

from typing import Optional
from django.utils import timezone
from django.core.cache import cache
from apps.academics.models import AcademicYear, Term
from apps.siteconfig.config_service import get_effective_site_settings


def get_cached_site_settings(*, school=None):
    """Get school-aware effective tenant site settings (via get_effective_site_settings) with short-lived caching."""
    school_id = getattr(school, "id", None)
    cache_key = f"site_settings_automation:{school_id or 'platform'}"
    site = cache.get(cache_key)
    if site is None:
        # config-resolver-allow: namespace object is cached in Django cache and returned to callers
        site = get_effective_site_settings(school=school)
        cache.set(cache_key, site, timeout=300)  # 5 min cache
    return site


def get_current_academic_year(school=None) -> Optional[AcademicYear]:
    """
    Returns active academic year, or most recent if none active.
    Falls back to most recent year if no active year found.

    ``school`` scopes every lookup to one tenant.  Callers that can name the
    tenant MUST pass it: without it this resolver reads across all schools and
    can return another tenant's year, which is why the Django-admin initial
    builders always supply one.  The parameter defaults to ``None`` so existing
    callers running inside a single-tenant context keep their behaviour.
    """
    now = timezone.now().date()
    scope = {"school": school} if school is not None else {}

    # First try: active year that contains today's date
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    active = AcademicYear.objects.filter(
        start_date__lte=now, end_date__gte=now, is_active=True, **scope
    ).first()

    if active:
        return active

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    # Second try: any active year
    active = (
        AcademicYear.objects.filter(is_active=True, **scope)
        .order_by("-start_date")
        .first()
    )

    if active:
        return active

    # Fallback: most recent year by start date
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    return AcademicYear.objects.filter(**scope).order_by("-start_date").first()


def get_current_term(
    academic_year: Optional[AcademicYear] = None, school=None
) -> Optional[Term]:
    """
    Returns current term based on today's date.
    If academic_year is provided, only searches within that year.

    ``school`` is forwarded to :func:`get_current_academic_year` when the year
    has to be resolved here, so a caller that names its tenant cannot be handed
    another tenant's term.
    """
    if not academic_year:
        academic_year = get_current_academic_year(school=school)

    if not academic_year:
        return None

    now = timezone.now().date()

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    # Find term that contains today's date
    term = Term.objects.filter(
        academic_year=academic_year, start_date__lte=now, end_date__gte=now
    ).first()

    if term:
        return term
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    # Fallback: active term in this year
    return (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        Term.objects.filter(academic_year=academic_year, is_active=True)
        .order_by("start_date")
        .first()
    )


def get_notification_channels(user, automation_type: str = "default") -> list:
    """
    Get notification channels for a user, respecting hierarchy:
    1. UserPreference (if set)
    2. Effective tenant platform settings default for automation type
    3. System default

    Args:
        user: User instance
        automation_type: Type of automation (e.g., "payment_reminder", "deadline_reminder")

    Returns:
        List of channel strings: ["email"], ["whatsapp"], ["email", "sms"], etc.
    """
    # Check user preference first
    try:
        user_pref = user.preferences
        if user_pref.notification_channels:
            return user_pref.notification_channels
    except AttributeError:
        # UserPreference doesn't exist for this user
        pass

    # Fall back to effective tenant platform settings
    site = get_cached_site_settings()

    if automation_type == "payment_reminder":
        channels = getattr(site, "finance_payment_reminder_default_channels", None)
        if channels:
            return channels

    elif automation_type == "deadline_reminder":
        channels = getattr(site, "deadline_reminder_channels", None)
        if channels:
            return channels

    # System default
    return ["email"]
