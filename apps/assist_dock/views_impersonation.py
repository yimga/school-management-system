"""v4.00.97 Wave G2 — impersonation views (dual-control + audit + session swap)."""

from __future__ import annotations

import json
import logging

from services.http_auth_guards import login_required_api as login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .impersonation import (
    GRANT_DEFAULT_TTL_SECONDS,
    GRANT_MAX_TTL_SECONDS,
    GRANT_REASON_MAX_LEN,
    ImpersonationGrant,
    ImpersonationGrantStatus,
    approve_grant,
    is_super,
    request_grant,
    revoke_grant,
    session_banner_context,
    start_session_from_grant,
    stop_session,
)

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 4096  # magic-number-allow: byte-size-cap


def _client_ip(request) -> str:
    """Best-effort client IP. Honors X-Forwarded-For when present."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",", 1)[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "")[:45]


def _user_agent(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:256]


def _require_super(view):
    """Decorator: 403 if the caller isn't a SUPERADMIN."""
    from functools import wraps

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not is_super(request.user):
            return HttpResponseForbidden("super required")
        return view(request, *args, **kwargs)

    return _wrapped


def _parse_json_body(request):
    raw = request.body or b""
    if len(raw) > _MAX_BODY_BYTES:
        return None, HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None, HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return None, HttpResponseBadRequest("body must be object")
    return body, None


@login_required
@_require_super
@require_safe
def impersonation_picker(request):
    """Wave G2 — SUPERADMIN-only landing page that surfaces:

      * Pending grants awaiting another super's approval.
      * APPROVED grants ready for the picker-user to start.
      * Recent CONSUMED / EXPIRED / REVOKED grants for audit visibility.
    """
    try:
        pending = list(
            ImpersonationGrant.objects.filter(
                status=ImpersonationGrantStatus.REQUESTED
            )
            .order_by("-created_at")[:25]
            .select_related("grantor", "target")
        )
        ready = list(
            ImpersonationGrant.objects.filter(
                status=ImpersonationGrantStatus.APPROVED
            )
            .order_by("-approved_at")[:25]
            .select_related("grantor", "target", "approver")
        )
        recent = list(
            ImpersonationGrant.objects.exclude(
                status=ImpersonationGrantStatus.REQUESTED
            )
            .exclude(status=ImpersonationGrantStatus.APPROVED)
            .order_by("-created_at")[:25]
            .select_related("grantor", "target", "approver")
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("impersonation_picker: queryset failed: %s", exc)
        pending, ready, recent = [], [], []
    return render(
        request,
        "assist_dock/power/impersonation_picker.html",
        {
            "pending_grants": pending,
            "ready_grants": ready,
            "recent_grants": recent,
            "active_session": session_banner_context(request),
            "default_ttl_seconds": GRANT_DEFAULT_TTL_SECONDS,
            "max_ttl_seconds": GRANT_MAX_TTL_SECONDS,
            "max_reason_len": GRANT_REASON_MAX_LEN,
        },
    )


@login_required
@_require_super
@require_http_methods(["POST"])
@csrf_protect
def impersonation_request(request):
    """POST {target_user_id, reason, ttl_seconds?} → create REQUESTED grant."""
    body, err = _parse_json_body(request)
    if err is not None:
        return err
    code, grant = request_grant(
        grantor=request.user,
        target_user_id=int(body.get("target_user_id") or 0),
        reason=str(body.get("reason") or ""),
        ttl_seconds=body.get("ttl_seconds"),
    )
    if code != "ok":
        return JsonResponse({"ok": False, "error": code}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "grant_id": grant.pk,
            "status": grant.status,
            "expires_at": grant.expires_at.isoformat() if grant.expires_at else "",
        }
    )


@login_required
@_require_super
@require_http_methods(["POST"])
@csrf_protect
def impersonation_approve(request):
    """POST {grant_id} → promote REQUESTED to APPROVED (approver != grantor)."""
    body, err = _parse_json_body(request)
    if err is not None:
        return err
    code, grant = approve_grant(
        approver=request.user, grant_id=int(body.get("grant_id") or 0)
    )
    if code != "ok":
        status_code = 403 if code == "dual_control_violation" else 400
        return JsonResponse({"ok": False, "error": code}, status=status_code)
    return JsonResponse(
        {"ok": True, "grant_id": grant.pk, "status": grant.status}
    )


@login_required
@_require_super
@require_http_methods(["POST"])
@csrf_protect
def impersonation_revoke(request):
    """POST {grant_id} → mark REVOKED."""
    body, err = _parse_json_body(request)
    if err is not None:
        return err
    code, grant = revoke_grant(
        actor=request.user, grant_id=int(body.get("grant_id") or 0)
    )
    if code != "ok":
        return JsonResponse({"ok": False, "error": code}, status=400)
    return JsonResponse(
        {"ok": True, "grant_id": grant.pk, "status": grant.status}
    )


@login_required
@_require_super
@require_http_methods(["POST"])
@csrf_protect
def impersonation_start(request):
    """POST {grant_id} → consume grant + install impersonation in session."""
    body, err = _parse_json_body(request)
    if err is not None:
        return err
    code, session = start_session_from_grant(
        operator=request.user,
        grant_id=int(body.get("grant_id") or 0),
        request_session=getattr(request, "session", None),
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    if code != "ok":
        return JsonResponse({"ok": False, "error": code}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "session_id": session.pk,
            "target_user_id": session.target_id,
            "started_at": session.started_at.isoformat()
            if session.started_at
            else "",
        }
    )


@login_required
@require_http_methods(["POST"])
@csrf_protect
def impersonation_stop(request):
    """POST → end the active impersonation in this session.

    NOT super-gated — the target user themselves should be able to "log out
    of impersonation" if it somehow lands on their account, and any caller
    with the session cookie should be able to end it.
    """
    code, info = stop_session(
        operator=request.user, request_session=getattr(request, "session", None)
    )
    if code != "ok":
        return JsonResponse({"ok": False, "error": code}, status=400)
    return JsonResponse({"ok": True, **info})


@login_required
@require_safe
def impersonation_banner_state(request):
    """GET — JSON describing whether impersonation is active in this session.

    Cheap polling endpoint for the floating banner (the middleware writes
    a template var; this endpoint is for any client-side surface that
    wants the same state).
    """
    return JsonResponse(session_banner_context(request) or {"active": False})


@login_required
@require_http_methods(["POST"])
@csrf_protect
def impersonation_stop_and_redirect(request):
    """Form-style stop button → POST then 302 to ``next`` (default ``/``)."""
    stop_session(
        operator=request.user, request_session=getattr(request, "session", None)
    )
    next_url = request.POST.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    return redirect(next_url)
