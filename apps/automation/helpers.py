"""
Helper functions for automation tasks.
"""

from typing import Optional
from django.utils import timezone
from django.core.cache import cache
from apps.academics.models import AcademicYear, Term
from apps.platform_runtime.helpers import get_effective_site_settings


def get_cached_site_settings(*, school=None):
    """Get school-aware SiteSettings with short-lived caching for automation tasks."""
    school_id = getattr(school, "id", None)
    cache_key = f"site_settings_automation:{school_id or 'platform'}"
    site = cache.get(cache_key)
    if site is None:
        site = get_effective_site_settings(school=school)
        cache.set(cache_key, site, timeout=300)  # 5 min cache
    return site


def get_current_academic_year() -> Optional[AcademicYear]:
    """
    Returns active academic year, or most recent if none active.
    Falls back to most recent year if no active year found.
    """
    now = timezone.now().date()

    # First try: active year that contains today's date
    active = AcademicYear.objects.filter(
        start_date__lte=now, end_date__gte=now, is_active=True
    ).first()

    if active:
        return active

    # Second try: any active year
    active = AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()

    if active:
        return active

    # Fallback: most recent year by start date
    return AcademicYear.objects.order_by("-start_date").first()


def get_current_term(academic_year: Optional[AcademicYear] = None) -> Optional[Term]:
    """
    Returns current term based on today's date.
    If academic_year is provided, only searches within that year.
    """
    if not academic_year:
        academic_year = get_current_academic_year()

    if not academic_year:
        return None

    now = timezone.now().date()

    # Find term that contains today's date
    term = Term.objects.filter(
        academic_year=academic_year, start_date__lte=now, end_date__gte=now
    ).first()

    if term:
        return term

    # Fallback: active term in this year
    return (
        Term.objects.filter(academic_year=academic_year, is_active=True)
        .order_by("start_date")
        .first()
    )


def get_notification_channels(user, automation_type: str = "default") -> list:
    """
    Get notification channels for a user, respecting hierarchy:
    1. UserPreference (if set)
    2. SiteSettings default for automation type
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

    # Fall back to SiteSettings
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
