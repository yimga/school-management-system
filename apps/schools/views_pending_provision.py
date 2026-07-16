"""Public read-only provisioning progress for pending tenant subdomains (no login)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


def _resolve_pending_school(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    try:
        from apps.schools.pending_tenant_discovery import (
            lookup_school_by_slug_or_subdomain,
            pending_school_state,
        )
        from apps.schools.middleware import _extract_subdomain
        from django.conf import settings

        host = (request.get_host() or "").split(":", 1)[0]
        base_domain = getattr(settings, "MULTI_TENANT_BASE_DOMAIN", None) or "runmycampus.com"
        token = _extract_subdomain(host, base_domain)
        if not token:
            return None
        school = lookup_school_by_slug_or_subdomain(token)
        if school is None or not pending_school_state(school):
            return None
        request.school = school
        request.tenant_provisioning_pending = True
        return school
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _public_progress_payload(school) -> dict:
    from apps.schools.provisioning_progress import resolve_provisioning_progress
    from apps.schools.provision_email_urls import build_tenant_authentication_url

    payload = resolve_provisioning_progress(school, include_dashboard_href=False)
    payload.pop("events", None)
    payload.pop("dashboard_href", None)
    if payload.get("portal_ready"):
        payload["tenant_login_url"] = build_tenant_authentication_url(
            school, "/authentication/login/"
        )
    return payload


def _maybe_kick_stalled_provisioning(request: HttpRequest, school) -> None:
    """Re-drive provisioning when the poll shows a dead/failed run or no run yet.

    The canonical heartbeat-aware, single-flighted resume lives in
    ``provision_watchdog.resume_provision_if_stuck`` — it judges liveness by
    heartbeat staleness (not the coarse 15-min ``stuck`` flag), cancels the dead
    zombie run, and re-drives via a background daemon thread with an atomic
    per-school lock. That replaces the old ``force=True`` re-kick, which bypassed
    both the in-flight guard AND the cooldown and so spawned a fresh migrate thread
    on EVERY poll once ``stuck`` tripped (a thundering herd on one schema).
    """
    try:
        from apps.schools.provisioning_progress import resolve_portal_ready
        from apps.schools.provision_watchdog import resume_provision_if_stuck

        if resolve_portal_ready(school):
            return
        result = resume_provision_if_stuck(school, reason="pending-poll")
        # resume_provision_if_stuck returns action ∈ {resumed, capped, error, none}
        # (settled/in_flight/debounced are all action="none" with the reason in
        # `reason`). For everything except `error` the watchdog already did the right
        # thing (kicked a resume, hit the cap, or had nothing to do) — don't also fire
        # the legacy kick. Only on `error` (its background kick raised) do we fall back.
        if result.get("action") != "error":
            return
        from apps.schools.pending_tenant_discovery import kick_pending_tenant_provisioning

        progress = _public_progress_payload(school)
        if progress.get("workflow_run_id") is None and int(
            progress.get("progress_percent") or 0
        ) <= 10:
            kick_pending_tenant_provisioning(request, school)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass


@require_GET
def api_public_pending_provision_progress(request: HttpRequest) -> JsonResponse:
    """
    Anonymous poll for ``{slug}.runmycampus.com`` while the campus is still provisioning.

    Returns the same canonical contract as owner/tenant APIs minus PII and dashboard href.
    """
    school = _resolve_pending_school(request)
    if school is None:
        return JsonResponse({"ok": False, "error": "not_pending"}, status=404)
    _maybe_kick_stalled_provisioning(request, school)
    return JsonResponse(_public_progress_payload(school))
