"""Require MFA enrollment for control-plane operators on the manager host."""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


OPERATOR_MFA_EXEMPT_PREFIXES = (
    "/authentication/login",
    "/authentication/logout",
    "/authentication/operator-invite/",
    "/authentication/mfa/",
    "/authentication/profile/security/",
    "/static/",
    "/health",
    "/healthz/",
    "/ready/",
    "/ws/wal/",  # JSON stub only on WSGI; exempt from MFA redirect loop
)


class OperatorMfaRequiredMiddleware(MiddlewareMixin):
    """
    When OPERATOR_MFA_REQUIRED_ON_MANAGER is True, block /super/ and /admin/
    until the operator enrolls MFA (TOTP or passkey), then until session MFA verify.
    """

    def process_request(self, request):
        from django.conf import settings

        if not getattr(settings, "OPERATOR_MFA_REQUIRED_ON_MANAGER", True):
            return None
        if getattr(request, "public_host_kind", None) != "manager":
            return None
        path = (request.path or "").strip()
        for prefix in OPERATOR_MFA_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return None
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        try:
            from apps.schools.control_plane import user_has_control_plane_access
            from apps.platform_runtime.operator_identity import operator_mfa_enrolled
            from apps.accounts.middleware import RequireMFAMiddleware
        except ImportError:
            return None
        if not user_has_control_plane_access(user):
            return None
        if not (path.startswith("/super/") or path.startswith("/admin/")):
            return None
        if not operator_mfa_enrolled(user):
            try:
                setup_url = reverse("accounts:mfa_setup")
            except Exception:
                setup_url = reverse("accounts:user_profile") + "#mfa-security"
            if not path.startswith(setup_url.rstrip("/")):
                return redirect(setup_url + "?next=" + path)
            return None
        if not RequireMFAMiddleware._is_mfa_verified(request):
            try:
                verify_url = reverse("accounts:mfa_verify")
            except Exception:
                return None
            if path != verify_url.rstrip("/") and not path.endswith(verify_url):
                return redirect(verify_url + "?next=" + path)
        return None
