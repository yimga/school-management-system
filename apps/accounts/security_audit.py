"""
Security & Identity Powerhouse: log security events, dedupe, GeoIP, lockdown.
Plan 3.15–3.16, improvements 3.23.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.exceptions import ObjectDoesNotExist
from django.core.signing import BadSignature
from django.db import DatabaseError
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

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
        from geoip2.errors import GeoIP2Error
        import os
    except ImportError:
        return {}
    path = os.getenv("GEOIP2_DB_PATH") or "/usr/share/GeoIP/GeoLite2-City.mmdb"
    if not os.path.isfile(path):
        return {}
    try:
        with geoip2.database.Reader(path) as reader:
            rec = reader.city(ip)
            out = {
                "city": getattr(rec, "city", None) and rec.city.name or "",
                "country": getattr(rec, "country", None) and rec.country.name or "",
                "country_code": getattr(rec, "country", None) and rec.country.iso_code or "",
            }
            loc = getattr(rec, "location", None)
            if loc is not None:
                lat = getattr(loc, "latitude", None)
                lon = getattr(loc, "longitude", None)
                if lat is not None and lon is not None:
                    out["latitude"] = float(lat)
                    out["longitude"] = float(lon)
            return out
    except (AttributeError, GeoIP2Error, OSError, TypeError, ValueError):
        return {}
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
        except (AttributeError, ObjectDoesNotExist):
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
    except (AttributeError, BadSignature, DatabaseError, KeyError, TypeError, ValueError) as e:
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

    _notify_admin_lockdown(user, school, initiator)

    return True


# World Engine: impossible travel threshold (km/h). Above this → lockdown.
IMPOSSIBLE_TRAVEL_SPEED_KMH = 1000


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in km between two (lat, lon) points."""
    import math
    R = 6371  # Earth radius km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def check_impossible_travel(request, user):
    """
    World Engine: after login, if previous login location implies speed > IMPOSSIBLE_TRAVEL_SPEED_KMH,
    trigger account lockdown and log IMPOSSIBLE_TRAVEL. Call from login view after log_security_event(LOGIN).
    """
    from apps.accounts.models import SecurityAuditLog

    if not request or not user:
        return
    ip = _get_client_ip(request)
    location_data = _get_location_data(ip) if ip else {}
    lat = location_data.get("latitude")
    lon = location_data.get("longitude")
    if lat is None or lon is None:
        return
    now = timezone.now()
    # Previous LOGIN (the one before the one we just created)
    prev = (
        SecurityAuditLog.objects.filter(
            user=user,
            event_type=SecurityAuditLog.EventType.LOGIN,
        )
        .order_by("-created_at")[1:2]
        .first()
    )
    if not prev:
        return
    prev_ts = prev.created_at
    prev_loc = getattr(prev, "location_data", None) or {}
    prev_lat = prev_loc.get("latitude")
    prev_lon = prev_loc.get("longitude")
    if prev_lat is None or prev_lon is None:
        return
    try:
        distance_km = _haversine_km(prev_lat, prev_lon, lat, lon)
        delta = (now - prev_ts).total_seconds() / 3600.0  # hours
        if delta <= 0:
            return
        speed_kmh = distance_km / delta
        if speed_kmh >= IMPOSSIBLE_TRAVEL_SPEED_KMH:
            logger.warning(
                "Impossible travel: user_id=%s distance_km=%.0f time_h=%.2f speed_kmh=%.0f",
                user.pk, distance_km, delta, speed_kmh,
            )
            log_security_event(
                user,
                SecurityAuditLog.EventType.IMPOSSIBLE_TRAVEL,
                request=request,
                school=getattr(request, "school", None),
                is_suspicious=True,
                initiator="self",
            )
            lockdown_user_account(user, request=request, initiator="self", school=getattr(request, "school", None))
    except (AttributeError, DatabaseError, TypeError, ValueError) as e:
        log_exception_with_context(
            "security_audit: check_impossible_travel failed",
            school_id=getattr(getattr(request, "school", None), "id", None),
            extra={"section": "check_impossible_travel", "user_id": getattr(user, "pk", None), "error": str(e)},
        )
        logger.exception("check_impossible_travel: %s", e)


def _notify_admin_lockdown(user, school, initiator):
    """Notify school admin of lockdown (placeholder: extend with email/sms)."""
    logger.info("Lockdown: user_id=%s school_id=%s initiator=%s", user.pk, getattr(school, "pk", None), initiator)
