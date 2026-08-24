"""
Hard minimum security strength — blocks platform use until score meets role baseline.

Works with quarterly review middleware (soft) and MFA middleware (factor enrollment).
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.platform_access_policy import (
    MINIMUM_STRENGTH_EXEMPT_VIEW_NAMES,
    user_meets_platform_security_minimum,
)

# Tenant school-setup surfaces must stay reachable while an admin improves posture.
_MINIMUM_STRENGTH_EXEMPT_PATH_PREFIXES = (
    "/school/setup/migration-cloud/",
)


class MinimumSecurityStrengthMiddleware:
    """Redirect users below required security score to profile security center."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "SECURITY_ENFORCE_MINIMUM_STRENGTH", True):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
            return self.get_response(request)

        match = getattr(request, "resolver_match", None)
        view_name = getattr(match, "view_name", None) if match else None
        if view_name in MINIMUM_STRENGTH_EXEMPT_VIEW_NAMES:
            return self.get_response(request)

        path = (request.path or "").strip()
        for prefix in _MINIMUM_STRENGTH_EXEMPT_PATH_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        # Platform operators use operator MFA + tier scopes, not tenant posture gates.
        try:
            from apps.platform_runtime.operator_identity import user_is_platform_operator

            if user_is_platform_operator(user):
                return self.get_response(request)
        except ImportError:
            pass

        school = getattr(request, "school", None)
        allowed, _reason, evaluation = user_meets_platform_security_minimum(
            user, school=school
        )
        request.rmc_security_evaluation = evaluation  # noqa: B018 — template bridge

        if allowed:
            return self.get_response(request)

        # Tenant hosts (subdomain, custom domain, sovereign appliance): show posture
        # banners and the profile gauge but never hard-lock the whole school portal.
        # Admins must reach Migration Cloud, backend dashboards, and imports while
        # improving MFA/recovery; hard redirect is reserved for non-tenant surfaces.
        if getattr(request, "is_tenant_host", False):
            return self.get_response(request)

        profile_url = reverse("accounts:user_profile")
        target = f"{profile_url}#profile-security-strength"
        path = request.get_full_path()
        if url_has_allowed_host_and_scheme(path, allowed_hosts={request.get_host()}):
            return redirect(f"{target}?next={path}&reason=minimum_strength")
        return redirect(f"{target}?reason=minimum_strength")
