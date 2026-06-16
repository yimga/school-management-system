"""Remote Support P2 — HTTP endpoints (JSON) for the online support loop.

Tenant-facing: request_help, grant_consent. Operator-facing: operator_accept,
operator_end. Each is gated; the heavy lifting + audit lives in
``remote_support_service``. These return JSON so the tenant button / operator
dashboard can drive them; the actual button + consent banner are presentation.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.platform_runtime import remote_support_service as svc
from apps.platform_runtime.models_remote_support import RemoteSupportSession
from apps.platform_runtime.remote_support_access import (
    operator_can_remote_support,
    user_can_provide_school_support,
)


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _session_json(s) -> dict:
    return {
        "id": str(s.id),
        "status": s.status,
        "channel": s.channel,
        "consent_satisfied": s.consent_satisfied,
        "is_open": s.is_open,
    }


@require_POST
@login_required
def request_help(request):
    """Tenant user opens a remote-support request for their school."""
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseBadRequest("No tenant context.")
    reason = (request.POST.get("reason") or "").strip()
    session = svc.request_remote_support(
        school=school, requested_by=request.user, reason=reason
    )
    return JsonResponse({"ok": True, "session": _session_json(session)}, status=201)


@require_POST
@login_required
def grant_consent(request, session_id):
    """Tenant grants consent for an operator to assist (transparency gate)."""
    session = get_object_or_404(RemoteSupportSession, id=session_id)
    school = getattr(request, "school", None)
    if school is None or str(session.school_id) != str(getattr(school, "id", "")):
        raise PermissionDenied("This session belongs to a different tenant.")
    is_requester = bool(
        session.requested_by_id and session.requested_by_id == request.user.id
    )
    if not (is_requester or user_can_provide_school_support(request.user, school)):
        raise PermissionDenied(
            "Only the requester or a school admin may grant consent."
        )
    svc.record_consent(session=session, by_user=request.user)
    return JsonResponse({"ok": True, "session": _session_json(session)})


@require_POST
@login_required
def operator_accept(request, session_id):
    """Operator accepts a request (scope + tenant-assignment enforced)."""
    session = get_object_or_404(RemoteSupportSession, id=session_id)
    if not operator_can_remote_support(request.user, session.school):
        raise PermissionDenied("Not authorized to support this tenant.")
    svc.accept_remote_support(
        session=session,
        operator=request.user,
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    return JsonResponse({"ok": True, "session": _session_json(session)})


@require_POST
@login_required
def operator_end(request, session_id):
    """Operator ends the session with an audited summary."""
    session = get_object_or_404(RemoteSupportSession, id=session_id)
    if not operator_can_remote_support(request.user, session.school):
        raise PermissionDenied("Not authorized to support this tenant.")
    summary = (request.POST.get("summary") or "").strip()
    reason = (request.POST.get("reason") or "resolved").strip()
    svc.end_remote_support(
        session=session, actor=request.user, reason=reason, summary=summary
    )
    return JsonResponse({"ok": True, "session": _session_json(session)})
