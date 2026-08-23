"""
Access control utilities for IP and country-based restrictions.
Checks incoming requests against allow/deny lists.
World Engine §8: cache keys are tenant-scoped (prefix from get_tenant_cache_prefix).
"""

import logging
from typing import Tuple

from django.core.cache import cache
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Q
from django.utils import timezone

from apps.api.rate_limit import client_ip as _trusted_client_ip
from apps.compliance.models_audit import IPAccessRule, CountryAccessRule

logger = logging.getLogger(__name__)

_ACCESS_CONTROL_PREFIX_ERRORS = (ImportError, AttributeError, TypeError, ValueError)
_ACCESS_CONTROL_DB_ERRORS = (DatabaseError, OperationalError, ProgrammingError)


def _access_control_prefix():
    """Tenant-scoped prefix for access rule cache keys."""
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        return get_tenant_cache_prefix()
    except _ACCESS_CONTROL_PREFIX_ERRORS:
        return "public"


def check_ip_access(ip_address: str) -> Tuple[bool, str]:
    """
    Check if IP is allowed based on configured rules.
    Returns: (is_allowed: bool, reason: str)

    Logic:
    1. Check DENY rules first - if any match, deny immediately
    2. If ALLOW rules exist, IP must match at least one
    3. If no rules exist or only DENY rules, allow by default
    """
    if not ip_address:
        return True, "No IP address provided"

    # Handle case where table doesn't exist yet (migrations not run)
    try:
        # Quick check if table exists by trying to count
        IPAccessRule.objects.exists()
    except _ACCESS_CONTROL_DB_ERRORS:
        # Table doesn't exist - allow access (fail open)
        logger.debug("Access control table not initialized - allowing access")
        return True, "Access control table not initialized - allowing access"

    # Cache key includes tenant prefix and version so rule updates invalidate cached entries
    def _rules_version():
        prefix = _access_control_prefix()
        key = f"{prefix}:access_rules_version"
        ver = cache.get(key)
        if ver is None:
            ver = 1
            cache.set(key, ver, None)
        return ver

    prefix = _access_control_prefix()
    cache_key = f"{prefix}:ip_access:{ip_address}:v{_rules_version()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    now = timezone.now()

    # Get active rules (exclude expired ones)
    try:
        deny_rules = IPAccessRule.objects.filter(
            rule_type=IPAccessRule.RuleType.DENY, is_active=True
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))

        allow_rules = IPAccessRule.objects.filter(
            rule_type=IPAccessRule.RuleType.ALLOW, is_active=True
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
    except _ACCESS_CONTROL_DB_ERRORS:
        # Database error - allow access (fail open)
        logger.debug("Access control check failed - allowing access")
        return True, "Access control check failed - allowing access"

    # Check DENY rules first
    for rule in deny_rules:
        if rule.matches(ip_address):
            result = (
                False,
                f"IP blocked by deny rule: {rule.description or rule.ip_address}",
            )
            cache.set(cache_key, result, 300)  # Cache for 5 min
            return result

    # If ALLOW rules exist, must match at least one
    if allow_rules.exists():
        for rule in allow_rules:
            if rule.matches(ip_address):
                result = (
                    True,
                    f"IP allowed by rule: {rule.description or rule.ip_address}",
                )
                cache.set(cache_key, result, 300)
                return result
        # No ALLOW rule matched
        result = (False, "IP not in allow list")
        cache.set(cache_key, result, 300)
        return result

    # No rules or only DENY rules - allow by default
    result = (True, "No restrictions configured")
    cache.set(cache_key, result, 300)
    return result


def check_country_access(country_code: str) -> Tuple[bool, str]:
    """
    Check if country is allowed based on configured rules.
    Returns: (is_allowed: bool, reason: str)

    Logic: same as IP - DENY first, then ALLOW if rules exist.
    """
    if not country_code:
        return True, "No country code provided"

    # Normalize to uppercase
    country_code = country_code.upper()

    # Cache key includes tenant prefix and version
    def _rules_version():
        prefix = _access_control_prefix()
        key = f"{prefix}:access_rules_version"
        ver = cache.get(key)
        if ver is None:
            ver = 1
            cache.set(key, ver, None)
        return ver

    prefix = _access_control_prefix()
    cache_key = f"{prefix}:country_access:{country_code}:v{_rules_version()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Get active rules
    deny_rules = CountryAccessRule.objects.filter(
        rule_type=CountryAccessRule.RuleType.DENY,
        is_active=True,
        country_code=country_code,
    )

    allow_rules = CountryAccessRule.objects.filter(
        rule_type=CountryAccessRule.RuleType.ALLOW, is_active=True
    )

    # Check DENY
    if deny_rules.exists():
        result = (False, f"Country {country_code} is blocked")
        cache.set(cache_key, result, 300)
        return result

    # Check ALLOW
    if allow_rules.exists():
        if allow_rules.filter(country_code=country_code).exists():
            result = (True, f"Country {country_code} is allowed")
            cache.set(cache_key, result, 300)
            return result
        else:
            result = (False, f"Country {country_code} not in allow list")
            cache.set(cache_key, result, 300)
            return result

    # No rules - allow
    result = (True, "No country restrictions configured")
    cache.set(cache_key, result, 300)
    return result


def get_country_from_ip(ip_address: str) -> str | None:
    """
    Resolve country code from IP using GeoIP2 (if available).
    Returns ISO 3166-1 alpha-2 code or None.
    When GEOIP_PATH is not set (e.g. on Render), returns None so callers can fall back.
    """
    try:
        from django.contrib.gis.geoip2 import GeoIP2, GeoIP2Exception
    except ImportError:
        return None
    try:
        g = GeoIP2()
        country = g.country(ip_address)
        return country.get("country_code")
    except (GeoIP2Exception, AttributeError, TypeError, ValueError, OSError):
        # GeoIP2 not configured (no GEOIP_PATH), IP not found, or DB missing
        return None


def check_request_access(request) -> Tuple[bool, str]:
    """
    Comprehensive access check for a Django request.
    Checks both IP and country rules.
    Returns: (is_allowed: bool, reason: str)
    """
    # Client IP from the outermost TRUSTED proxy hop. X-Forwarded-For is
    # client-controlled to the LEFT, so a banned client could previously
    # prepend any unbanned address and walk straight through the perimeter
    # -- and defeat CountryAccessRule too, since the country is derived here.
    ip_address = _trusted_client_ip(request)
    if ip_address == "unknown":
        ip_address = None

    # Check IP access
    ip_allowed, ip_reason = check_ip_access(ip_address)
    if not ip_allowed:
        return False, ip_reason

    # Check country access (if GeoIP2 available)
    country_code = get_country_from_ip(ip_address)
    if country_code:
        country_allowed, country_reason = check_country_access(country_code)
        if not country_allowed:
            return False, country_reason

    return True, "Access granted"
