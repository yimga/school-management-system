"""Remote Support P4 — reverse-channel HTTP endpoints.

Operator side: queue_intent. Tenant/hub side (polled on reconnect):
pending_intents, ack_intent, heartbeat, config_version.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.platform_runtime import remote_support_reverse_channel as svc
from apps.platform_runtime.models_remote_support import (
    OperatorIntent,
    RemoteSupportSession,
)
from apps.platform_runtime.remote_support_access import operator_can_remote_support
from apps.schools.models import School


@require_POST
@login_required
def queue_intent(request):
    """Operator queues a cloud->tenant intent (scope + assignment enforced)."""
    kind = (request.POST.get("kind") or "").strip()
    if kind not in OperatorIntent.Kind.values:
        return HttpResponseBadRequest("invalid kind")

    session = None
    session_id = request.POST.get("session_id")
    if session_id:
        session = get_object_or_404(RemoteSupportSession, id=session_id)
        school = session.school
    else:
        school_id = request.POST.get("school_id")
        if not school_id:
            return HttpResponseBadRequest("school_id or session_id required")
        school = get_object_or_404(School, id=school_id)

    if not operator_can_remote_support(request.user, school):
        raise PermissionDenied("Not authorized to support this tenant.")

    payload = {}
    raw = request.POST.get("payload")
    if raw:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return HttpResponseBadRequest("invalid payload json")
        if not isinstance(payload, dict):
            return HttpResponseBadRequest("payload must be an object")

    intent = svc.queue_operator_intent(
        school=school,
        created_by=request.user,
        kind=kind,
        payload=payload,
        reason=(request.POST.get("reason") or "").strip(),
        session=session,
    )
    return JsonResponse({"ok": True, "intent_id": str(intent.id)}, status=201)


@require_POST
@login_required
def pending_intents(request):
    """Tenant/hub polls for live intents (marks them delivered).

    POST (not GET): the poll mutates state (PENDING -> DELIVERED), so it must be
    CSRF-protected. A GET with side effects can be triggered cross-site and
    silently advance a tenant's intents, masking an operator message.
    """
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseBadRequest("No tenant context.")
    return JsonResponse(
        {"ok": True, "intents": svc.fetch_pending_intents(school=school)}
    )


@require_POST
@login_required
def ack_intent(request, intent_id):
    """Tenant/hub acknowledges (applied) an intent."""
    intent = get_object_or_404(OperatorIntent, id=intent_id)
    school = getattr(request, "school", None)
    if school is None or str(intent.school_id) != str(getattr(school, "id", "")):
        raise PermissionDenied("This intent belongs to a different tenant.")
    svc.acknowledge_intent(
        intent=intent,
        actor=request.user,
        note=(request.POST.get("note") or "").strip(),
    )
    return JsonResponse({"ok": True})


@require_POST
@login_required
def heartbeat(request):
    """Tenant/hub phone-home so operators can see online/offline."""
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseBadRequest("No tenant context.")
    try:
        pending = int(request.POST.get("pending_sync") or 0)
    except (ValueError, TypeError):
        pending = 0
    hb = svc.record_heartbeat(
        school=school,
        profile=(request.POST.get("profile") or "").strip(),
        app_version=(request.POST.get("app_version") or "").strip(),
        pending_sync=pending,
    )
    return JsonResponse({"ok": True, "online": hb.is_online()})


@require_GET
@login_required
def config_version(request):
    """Tenant/hub checks whether configuration changed (re-pull if differs)."""
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseBadRequest("No tenant context.")
    return JsonResponse({"ok": True, "version": svc.config_version_for(school)})
