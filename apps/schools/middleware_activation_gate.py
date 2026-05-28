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

        # v4.00.2 audit (2026-05-28): ``activation_first_action`` is only
        # registered in ``config.tenant_urls`` — the manager URLconf
        # (``config.urls``) does not include it. When the URL resolver
        # cache is stale (e.g. ``@override_settings(ROOT_URLCONF=...)`` in
        # tests, or a worker that loaded the resolver before a request
        # context switched URLconfs), ``reverse(...)`` raises
        # NoReverseMatch and the prior bare ``except: return None`` made
        # the entire gate silently inert. Fall back to the literal path
        # so the gate works regardless of URLconf state.
        _ACTIVATION_FIRST_ACTION_PATH = "/activation/first-action/"
        try:
            target = reverse("activation_first_action").lower()
        except Exception:
            target = _ACTIVATION_FIRST_ACTION_PATH
        if path.rstrip("/") == target.rstrip("/"):
            return None
        try:
            url = reverse("activation_first_action")
        except Exception:
            url = _ACTIVATION_FIRST_ACTION_PATH
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
