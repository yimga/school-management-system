"""
PII masking (plan 3.21): full address/DOB masked until user re-authenticates.
Helper for profile views: show masked value unless session has recent re-auth.
"""
from __future__ import annotations


# Session key: set when user re-authenticates (e.g. password confirm); clear after short TTL or use
PII_REAUTH_SESSION_KEY = "pii_reauth_at"


def mask_address(address: str) -> str:
    if not address or not isinstance(address, str):
        return ""
    s = address.strip()
    if len(s) <= 8:
        return "****" if s else ""
    return s[:2] + "***" + s[-2:] if len(s) > 4 else "****"


def mask_date(date_obj) -> str:
    """Mask DOB for display (e.g. show only year or '**/**/YYYY')."""
    if date_obj is None:
        return ""
    try:
        from datetime import date
        if isinstance(date_obj, date):
            return f"**/**/{date_obj.year}"
    except (TypeError, AttributeError, ValueError):
        pass
    return "**/**/****"


def is_shadow_or_impersonation(request) -> bool:
    """
    Section 11.4: True when support is shadowing/impersonating a user.
    In these sessions PII must be masked (do not show full name, DOB, address, etc.).
    """
    if not getattr(request, "session", None):
        return False
    return bool(request.session.get("impersonation") or request.session.get("shadow_session"))


def can_show_pii(request) -> bool:
    """
    True if request session has recent PII re-auth (e.g. within last 5 minutes).
    Set PII_REAUTH_SESSION_KEY to timezone.now().isoformat() after user confirms password.
    When is_shadow_or_impersonation(request), returns False so PII stays masked.
    """
    if is_shadow_or_impersonation(request):
        return False
    from django.utils import timezone
    from datetime import timedelta
    reauth_at = request.session.get(PII_REAUTH_SESSION_KEY)
    if not reauth_at:
        return False
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(reauth_at.replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        if timezone.now() - dt > timedelta(minutes=5):
            return False
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def set_pii_reauth(request) -> None:
    """Call after user re-authenticates; allows PII to be shown for a short window."""
    from django.utils import timezone
    request.session[PII_REAUTH_SESSION_KEY] = timezone.now().isoformat()
    request.session.modified = True
