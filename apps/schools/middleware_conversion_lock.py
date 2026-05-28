"""
Strict conversion lock: block tenant traffic until first_action_completed (explicit signal).

Runs after AuthenticationMiddleware. Disabled unless settings.CONVERSION_LOCK_STRICT.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

class ConversionLockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redir = self._maybe_redirect(request)
        if redir is not None:
            return redir
        return self.get_response(request)

    def _maybe_redirect(self, request):
        if not getattr(settings, "CONVERSION_LOCK_STRICT", False):
            return None
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        # Manager (control-plane) host is for super-admin operations, not
        # tenant activation; the activation flow is enforced on the tenant
        # host where ``request.school`` is bound. Without this short-circuit
        # an operator with cross-tenant membership browsing manager pages
        # can hit / ↔ /activation/first-action/ redirect loops.
        if (getattr(request, "public_host_kind", None) or "").lower() == "manager":
            return None
        # v4.00.2 audit (2026-05-28): the prior bare ``getattr(request,
        # "school", None)`` bailed when no earlier middleware had attached
        # ``request.school`` (e.g. test environments using
        # ``ROOT_URLCONF="config.tenant_urls"`` without the tenant
        # resolution middleware wired in). Fall back to the canonical
        # ``resolve_request_school`` (request.school → session → signup
        # verification → primary membership) — same resolution chain
        # ActivationGateMiddleware uses.
        try:
            from apps.lifecycle.tenant_school_resolve import resolve_request_school

            school = resolve_request_school(request)
        except ImportError:
            school = getattr(request, "school", None)
        if school is None:
            return None
        if request.session.get("impersonation"):
            return None
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist
        from apps.schools.conversion_lock_state import (
            school_conversion_is_locked,
            school_first_action_completed,
        )

        if school_first_action_completed(school):
            return None
        if not school_conversion_is_locked(school, user=user):
            return None

        path = getattr(request, "path", "") or ""
        extra = getattr(settings, "CONVERSION_LOCK_ALLOWED_PREFIXES", ()) or ()
        if path_matches_conversion_allowlist(path, extra):
            return None
        # v4.00.2 audit — single SOT for the path + url-name (see
        # apps.schools.activation_views).
        from apps.schools.activation_views import (
            ACTIVATION_FIRST_ACTION_PATH,
            ACTIVATION_FIRST_ACTION_URL_NAME,
        )

        try:
            url = reverse(ACTIVATION_FIRST_ACTION_URL_NAME)
        except Exception:
            url = ACTIVATION_FIRST_ACTION_PATH
        if request.META.get("QUERY_STRING"):
            url = f"{url}?{request.META['QUERY_STRING']}"
        return HttpResponseRedirect(url)
