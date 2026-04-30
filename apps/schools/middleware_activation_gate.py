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
        school = getattr(request, "school", None)
        if school is None or not school_activation_gate_pending(school):
            return None

        if request.session.get("impersonation"):
            return None

        path = (getattr(request, "path", "") or "").lower()
        if self._path_exempt(path):
            return None

        try:
            target = reverse("activation_first_action").lower()
        except Exception:
            return None
        if path.rstrip("/") == target.rstrip("/"):
            return None
        try:
            url = reverse("activation_first_action")
            if request.META.get("QUERY_STRING"):
                url = f"{url}?{request.META['QUERY_STRING']}"
            return HttpResponseRedirect(url)
        except Exception:
            return None

    def _path_exempt(self, path: str) -> bool:
        prefixes = (
            "/authentication/",
            "/static/",
            "/media/",
            "/activation/",
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
