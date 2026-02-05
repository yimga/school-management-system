"""
Access control utilities for IP and country-based restrictions.
Checks incoming requests against allow/deny lists.
"""

from typing import Tuple
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from apps.compliance.models_audit import IPAccessRule, CountryAccessRule


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
    except Exception:
        # Table doesn't exist - allow access (fail open)
        return True, "Access control table not initialized - allowing access"

    # Cache key includes a version so rule updates invalidate cached entries
    def _rules_version():
        ver = cache.get('access_rules_version')
        if ver is None:
            ver = 1
            cache.set('access_rules_version', ver, None)
        return ver

    cache_key = f"ip_access:{ip_address}:v{_rules_version()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    now = timezone.now()

    # Get active rules (exclude expired ones)
    try:
        deny_rules = IPAccessRule.objects.filter(
            rule_type=IPAccessRule.RuleType.DENY,
            is_active=True
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))

        allow_rules = IPAccessRule.objects.filter(
            rule_type=IPAccessRule.RuleType.ALLOW,
            is_active=True
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
    except Exception:
        # Database error - allow access (fail open)
        return True, "Access control check failed - allowing access"

    # Check DENY rules first
    for rule in deny_rules:
        if rule.matches(ip_address):
            result = (False, f"IP blocked by deny rule: {rule.description or rule.ip_address}")
            cache.set(cache_key, result, 300)  # Cache for 5 min
            return result

    # If ALLOW rules exist, must match at least one
    if allow_rules.exists():
        for rule in allow_rules:
            if rule.matches(ip_address):
                result = (True, f"IP allowed by rule: {rule.description or rule.ip_address}")
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

    # Cache key includes a version so rule updates invalidate cached entries
    def _rules_version():
        ver = cache.get('access_rules_version')
        if ver is None:
            ver = 1
            cache.set('access_rules_version', ver, None)
        return ver

    cache_key = f"country_access:{country_code}:v{_rules_version()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Get active rules
    deny_rules = CountryAccessRule.objects.filter(
        rule_type=CountryAccessRule.RuleType.DENY,
        is_active=True,
        country_code=country_code
    )

    allow_rules = CountryAccessRule.objects.filter(
        rule_type=CountryAccessRule.RuleType.ALLOW,
        is_active=True
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
    """
    try:
        from django.contrib.gis.geoip2 import GeoIP2
        g = GeoIP2()
        country = g.country(ip_address)
        return country.get("country_code")
    except Exception:
        # GeoIP2 not configured or IP not found
        return None


def check_request_access(request) -> Tuple[bool, str]:
    """
    Comprehensive access check for a Django request.
    Checks both IP and country rules.
    Returns: (is_allowed: bool, reason: str)
    """
    # Get IP from request
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.META.get("REMOTE_ADDR")

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
