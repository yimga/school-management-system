# Phase G optional: Sync Center UI – list SyncConflict for school, resolve server/client/discard
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from apps.accounts.decorators import login_required, permission_required


def _resolve_sync_conflict(conflict, resolution, resolved_by):
    from django.utils import timezone
    from .models import SyncConflict

    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = resolution
    if resolution == SyncConflict.Status.RESOLVED_CLIENT:
        from apps.api.sync_services import _get_entity_config

        config = _get_entity_config()
        if conflict.entity_type in config:
            model, allowed = config[conflict.entity_type]
            updates = {
                k: v for k, v in (conflict.client_data or {}).items() if k in allowed
            }
            if updates:
                try:
                    instance = model.objects.get(pk=conflict.entity_id)
                    for key, value in updates.items():
                        setattr(instance, key, value)
                    instance.save(update_fields=list(updates.keys()) + ["updated_at"])
                except model.DoesNotExist:
                    pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def sync_center(request):
    """List SyncConflict for request.school; link to resolve from UI or admin."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school to view sync conflicts.")
        return redirect("portal:home")
    try:
        from .models import SyncConflict
    except ImportError:
        action_url = reverse("accounts:backend_dashboard")
        return render(
            request,
            "siteconfig/sync_center.html",
            {
                "school": school,
                "conflicts": [],
                "sync_available": False,
                "action_url": action_url,
                "action_text": "Back to dashboard",
            },
        )
    conflicts = SyncConflict.objects.filter(school=school).order_by("-created_at")[:50]
    return render(
        request,
        "siteconfig/sync_center.html",
        {
            "school": school,
            "conflicts": conflicts,
            "sync_available": True,
        },
    )


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def sync_center_resolve(request, conflict_id):
    """Resolve one conflict: resolution=server|client|discard."""
    school = getattr(request, "school", None)
    if not school:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "No school"}, status=403)
        return redirect("portal:home")
    try:
        from .models import SyncConflict
    except ImportError:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": "SyncConflict not available"}, status=404
            )
        return redirect("siteconfig:sync_center")
    conflict = get_object_or_404(SyncConflict, pk=conflict_id, school=school)
    if conflict.status != SyncConflict.Status.PENDING:
        messages.info(request, "Conflict already resolved.")
        return redirect("siteconfig:sync_center")
    resolution_str = (request.POST.get("resolution") or "").strip().lower()
    if resolution_str == "server":
        resolution = SyncConflict.Status.RESOLVED_SERVER
    elif resolution_str == "client":
        resolution = SyncConflict.Status.RESOLVED_CLIENT
    elif resolution_str == "discard":
        resolution = SyncConflict.Status.DISCARDED
    else:
        messages.error(request, "Invalid resolution.")
        return redirect("siteconfig:sync_center")
    _resolve_sync_conflict(conflict, resolution, request.user)
    messages.success(request, f"Conflict resolved ({resolution_str}).")
    return redirect("siteconfig:sync_center")
