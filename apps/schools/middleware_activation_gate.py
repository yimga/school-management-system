"""
Redirect tenant users (all roles) to /activation/first-action/ while gate pending
when CONVERSION_LOCK_STRICT is off. When strict is on, ConversionLockMiddleware handles
dashboard blocking; this middleware is a no-op.
Runs after GrowthFunnelMiddleware so first substantive POST can clear the gate first.
"""

from __future__ import annotations

from django.conf import settings as dj_settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.schools.activation_gate import school_activation_gate_pending
from apps.schools.activation_views import activation_gate_enabled


class ActivationGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redir = self._maybe_redirect(request)
        if redir is not None:
            return redir
        return self.get_response(request)

    def _maybe_redirect(self, request):
        if getattr(dj_settings, "CONVERSION_LOCK_STRICT", False):
            return None
        if not activation_gate_enabled():
            return None
        if not getattr(request.user, "is_authenticated", False):
            return None
        # Manager (control-plane) host is for super-admin operations, not
        # tenant activation; suppressing here also breaks the / ↔ /activation/
        # cycle that occurs when an operator with cross-tenant membership
        # browses manager pages. The activation flow is enforced on the
        # tenant host where ``request.school`` is bound.
        if (getattr(request, "public_host_kind", None) or "").lower() == "manager":
            return None
        try:
            from apps.lifecycle.tenant_school_resolve import resolve_request_school
            from apps.lifecycle.wind_down import is_wind_down_mode

            school = resolve_request_school(request)
            if school is not None and is_wind_down_mode(school):
                return None
        except ImportError:
            school = getattr(request, "school", None)

        if school is None or not school_activation_gate_pending(school):
            return None

        if request.session.get("impersonation"):
            return None

        path = (getattr(request, "path", "") or "").lower()
        if self._path_exempt(path):
            return None

        # v4.00.2 audit — ``activation_first_action`` is registered in both
        # ``config.urls`` and ``config.tenant_urls``; the literal-path
        # fallback below is a defensive backstop for any edge case where
        # ``reverse(...)`` still fails (worker loaded URL resolver
        # pre-deploy, override_settings(ROOT_URLCONF=...) in tests). The
        # path + url-name come from the activation_views SOT so changing
        # the URL there propagates everywhere.
        from apps.schools.activation_views import (
            ACTIVATION_FIRST_ACTION_PATH,
            ACTIVATION_FIRST_ACTION_URL_NAME,
        )

        try:
            target = reverse(ACTIVATION_FIRST_ACTION_URL_NAME).lower()
        except Exception:
            target = ACTIVATION_FIRST_ACTION_PATH
        if path.rstrip("/") == target.rstrip("/"):
            return None
        try:
            url = reverse(ACTIVATION_FIRST_ACTION_URL_NAME)
        except Exception:
            url = ACTIVATION_FIRST_ACTION_PATH
        if request.META.get("QUERY_STRING"):
            url = f"{url}?{request.META['QUERY_STRING']}"
        return HttpResponseRedirect(url)

    def _path_exempt(self, path: str) -> bool:
        prefixes = (
            "/authentication/",
            "/static/",
            "/media/",
            "/activation/",
            "/school/studio/",
            "/siteconfig/onboarding",
            "/onboard/",
            "/health",
            "/healthz/",
            "/ready/",
            "/status/",
            "/metrics/",
            "/api/",
            "/ws/",
            "/favicon",
            "/admin/",
        )
        return any(path.startswith(p) for p in prefixes)
