"""
Security & Identity Powerhouse: log security events, dedupe, GeoIP, lockdown.
Plan 3.15–3.16, improvements 3.23.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

logger = logging.getLogger(__name__)

# Dedupe window: same user+ip+device within 1h → update last_seen
DEDUPE_WINDOW = timedelta(hours=1)


def _get_client_ip(request):
    """Use django-ipware if available, else request.META."""
    try:
        from ipware import get_client_ip
        ip, _ = get_client_ip(request)
        return ip
    except ImportError:
        return (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )


def _get_location_data(ip):
    """GeoIP: city/country (MaxMind or similar). Return dict with country_code for is_suspicious check."""
    if not ip:
        return {}
    try:
        import geoip2.database
        import os
        path = os.getenv("GEOIP2_DB_PATH") or "/usr/share/GeoIP/GeoLite2-City.mmdb"
        if os.path.isfile(path):
            with geoip2.database.Reader(path) as reader:
                rec = reader.city(ip)
                return {
                    "city": getattr(rec, "city", None) and rec.city.name or "",
                    "country": getattr(rec, "country", None) and rec.country.name or "",
                    "country_code": getattr(rec, "country", None) and rec.country.iso_code or "",
                }
    except Exception:
        pass
    return {}


def _anonymize_ip(ip: str) -> str:
    """Anonymize IP for GDPR (e.g. after 90 days): keep only first two octets for IPv4."""
    if not ip or ":" in ip:
        return ip[: min(len(ip), 10)] + "..." if ip else ""
    parts = ip.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}.0.0"
    return ip


def log_security_event(
    user,
    event_type: str,
    request=None,
    school=None,
    is_suspicious=None,
    initiator: str = "",
):
    """
    Create or dedupe SecurityAuditLog. If same user+ip+user_agent within DEDUPE_WINDOW,
    update last_seen on existing row instead of creating new one.
    """
    from apps.accounts.models import SecurityAuditLog

    ip = _get_client_ip(request) if request else None
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:500] if request else ""
    location_data = _get_location_data(ip) if ip else {}

    if school is None and request is not None:
        school = getattr(request, "school", None)

    if is_suspicious is None and school and location_data.get("country_code"):
        try:
            region_code = getattr(school.default_region, "code", None) or getattr(school.default_region, "country_code", None)
            if region_code and location_data.get("country_code") != region_code:
                is_suspicious = True
        except Exception:
            pass
    if is_suspicious is None:
        is_suspicious = False

    # Dedupe: same user, ip, event_type, within window
    since = timezone.now() - DEDUPE_WINDOW
    existing = (
        SecurityAuditLog.objects.filter(
            user=user,
            event_type=event_type,
            ip_address=ip,
            created_at__gte=since,
        )
        .order_by("-created_at")
        .first()
    )
    if existing and event_type == "LOGIN":
        existing.user_agent = user_agent
        existing.location_data = location_data
        existing.is_suspicious = is_suspicious
        existing.last_seen = timezone.now()
        existing.save(update_fields=["user_agent", "location_data", "is_suspicious", "last_seen"])
        return existing

    return SecurityAuditLog.objects.create(
        school=school,
        user=user,
        event_type=event_type,
        ip_address=ip,
        user_agent=user_agent,
        location_data=location_data,
        is_suspicious=is_suspicious,
        initiator=initiator or "self",
    )


def lockdown_user_account(user, request=None, initiator: str = "self", school=None):
    """
    Emergency Lockdown (plan 3.16): invalidate sessions, force password change, notify admin.
    Cooldown: 24h (check last_lockdown_at); optional recovery flow after.
    """
    from django.contrib.auth import update_session_auth_hash
    from apps.accounts.models import SecurityAuditLog, User

    if not user or not isinstance(user, User):
        return False

    # Cooldown: one lockdown per 24h per user
    if user.last_lockdown_at:
        if timezone.now() - user.last_lockdown_at < timedelta(hours=24):
            logger.warning("Lockdown cooldown: user %s attempted within 24h", user.pk)
            return False

    if school is None and request is not None:
        school = getattr(request, "school", None)

    user.requires_password_change = True
    user.last_lockdown_at = timezone.now()
    user.save(update_fields=["requires_password_change", "last_lockdown_at"])

    # Invalidate all sessions for this user (decode session_data to find _auth_user_id)
    try:
        uid = str(user.pk)
        for session in Session.objects.all():
            data = session.get_decoded()
            if data.get("_auth_user_id") == uid:
                session.delete()
    except Exception as e:
        logger.exception("Session purge failed: %s", e)
    if request and request.session.session_key:
        request.session.flush()

    log_security_event(
        user,
        SecurityAuditLog.EventType.LOCKDOWN_TRIGGERED,
        request=request,
        school=school,
        is_suspicious=True,
        initiator=initiator,
    )

    try:
        _notify_admin_lockdown(user, school, initiator)
    except Exception as e:
        logger.exception("Lockdown admin notify failed: %s", e)

    return True


def _notify_admin_lockdown(user, school, initiator):
    """Notify school admin of lockdown (placeholder: extend with email/sms)."""
    logger.info("Lockdown: user_id=%s school_id=%s initiator=%s", user.pk, getattr(school, "pk", None), initiator)
