"""
Block operational tenant navigation while Phase B seed is still incomplete.

Phase A flips ``is_active`` so the subdomain resolves and progress APIs work,
but grades/finance/structure still 500 until seed finishes. Document navigations
are redirected to ``tenant_provisioning_status`` until ``phase_b_complete``.

IMPORTANT: gate ONLY on the explicit Phase A / Phase B markers written by the
provisioning pipeline. Do NOT use ``provisioning_needs_resume`` here — that
helper also returns True for marker-less schools whose workspace probe is
``False`` (coverage below floor after a failed/partial ``migrate_schemas``).
Wiring that probe into HTTP middleware trapped established schools behind the
provisioning page after a successful login (looks like "cannot sign in").
Healers / reconciler / Requeue still use ``provisioning_needs_resume``.
"""

from __future__ import annotations

from django.http import HttpResponseRedirect
from django.urls import NoReverseMatch, reverse


def _phase_a_awaiting_phase_b(school) -> bool:
    """True only when Phase A activated the portal and Phase B never finished."""
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return False
    prov = raw.get("provisioning")
    if not isinstance(prov, dict):
        return False
    return bool(prov.get("phase_a_complete")) and not bool(prov.get("phase_b_complete"))


class ProvisioningSeedGateMiddleware:
    """PGL-001 seal: no Phase-A husk operational shell until Phase B completes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redir = self._maybe_redirect(request)
        if redir is not None:
            return redir
        return self.get_response(request)

    def _maybe_redirect(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return None
        if (getattr(request, "public_host_kind", None) or "").lower() == "manager":
            return None
        if request.session.get("impersonation"):
            return None

        try:
            from apps.lifecycle.tenant_school_resolve import resolve_request_school

            school = resolve_request_school(request)
        except ImportError:
            school = getattr(request, "school", None)
        if school is None:
            return None

        if not _phase_a_awaiting_phase_b(school):
            return None

        path = (getattr(request, "path", "") or "").lower()
        if self._path_exempt(path):
            return None

        from apps.schools.gate_request_kind import is_document_navigation

        if not is_document_navigation(request):
            return None

        try:
            url = reverse("tenant_provisioning_status")
        except NoReverseMatch:
            url = "/school/studio/provisioning/"
        target = url.lower().rstrip("/")
        if path.rstrip("/") == target:
            return None
        # Never forward QUERY_STRING (especially ?auto=1): tenant_provisioning_status
        # auto-redirects live portals to School Studio, which is not exempt → loop.
        return HttpResponseRedirect(url)

    def _path_exempt(self, path: str) -> bool:
        # Login/credential paths only — never the backend/portal shell under
        # /authentication/backend/ (that is the husk 500 surface).
        auth_allow = (
            "/authentication/login",
            "/authentication/logout",
            "/authentication/password",
            "/authentication/legacy-setup",
            "/authentication/onboarding",
            "/authentication/mfa",
            "/authentication/verify",
            "/authentication/redirect",
        )
        if path.startswith("/authentication/"):
            return any(path.startswith(p) for p in auth_allow)

        prefixes = (
            "/static/",
            "/media/",
            "/activation/",
            "/school/studio/provisioning",
            "/api/school/lifecycle/provisioning",
            "/api/pending-provision/",
            "/api/",
            "/onboard/",
            "/health",
            "/healthz/",
            "/ready/",
            "/status/",
            "/metrics/",
            "/ws/",
            "/favicon",
            "/admin/",
        )
        return any(path.startswith(p) for p in prefixes)
