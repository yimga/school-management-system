"""Operator (/super/) remote-support surface.

Closes the cross-host gap: the tenant-facing remote-support endpoints live on the
tenant host, but operators work on the manager host. These mount the operator
actions (list open sessions, accept, end) on /super/ so an operator acts
same-host. Control-plane access is enforced by ``require_super_access_with_host``
(in super_urls.py); per-tenant scope is enforced by ``operator_can_remote_support``.
RemoteSupportSession is a SHARED (public-schema) model so it reads cleanly here.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.platform_runtime import remote_support_service as svc
from apps.platform_runtime.models_remote_support import RemoteSupportSession
from apps.platform_runtime.remote_support_access import operator_can_remote_support


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@require_GET
def super_remote_support_console(request):
    """Server-rendered operator console for open remote-support sessions.

    Control-plane page (extends control_plane_base.html). It carries no heavy
    query — the table hydrates from ``super:remote_support_sessions`` (sessions.json)
    via ``static/js/rmc-super-remote-support.js`` on a herd-safe poll loop. The
    accept / end POSTs the JS issues are still gated per-tenant by
    ``operator_can_remote_support`` inside the accept/end views, so this page
    never bypasses tenant isolation. Control-plane access is enforced by
    ``require_super_access_with_host`` in super_urls.py.
    """
    return render(
        request,
        "schools/super_remote_support_console.html",
        {
            "sessions_url": reverse("super:remote_support_sessions"),
            # Placeholder UUID is swapped client-side per row, mirroring how
            # _remote_support_banner.html templatizes per-session action URLs.
            "accept_url_template": reverse(
                "super:remote_support_accept",
                args=["00000000-0000-0000-0000-000000000000"],
            ),
            "end_url_template": reverse(
                "super:remote_support_end",
                args=["00000000-0000-0000-0000-000000000000"],
            ),
        },
    )


@require_GET
def super_remote_support_sessions(request):
    """Open remote-support sessions an operator can act on (newest first)."""
    sessions = RemoteSupportSession.objects.filter(  # tenant-isolation-allow: operator-control-plane-cross-tenant-support-queue
        status__in=RemoteSupportSession.OPEN_STATUSES
    ).order_by("-created_at")[:100]
    rows = [
        {
            "id": str(s.id),
            "school_id": str(s.school_id),
            "status": s.status,
            "channel": s.channel,
            "reason": s.reason,
            "needs_consent": (
                s.status == RemoteSupportSession.Status.ACCEPTED
                and not s.consent_satisfied
            ),
        }
        for s in sessions
    ]
    return JsonResponse({"ok": True, "sessions": rows})


@require_POST
def super_remote_support_accept(request, session_id):
    session = get_object_or_404(RemoteSupportSession, id=session_id)
    if not operator_can_remote_support(request.user, session.school):
        return JsonResponse({"ok": False, "error": "not_authorized"}, status=403)
    svc.accept_remote_support(
        session=session,
        operator=request.user,
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    return JsonResponse({"ok": True})


@require_POST
def super_remote_support_end(request, session_id):
    session = get_object_or_404(RemoteSupportSession, id=session_id)
    if not operator_can_remote_support(request.user, session.school):
        return JsonResponse({"ok": False, "error": "not_authorized"}, status=403)
    summary = (request.POST.get("summary") or "").strip()
    reason = (request.POST.get("reason") or "resolved").strip()
    svc.end_remote_support(
        session=session, actor=request.user, reason=reason, summary=summary
    )
    return JsonResponse({"ok": True})
