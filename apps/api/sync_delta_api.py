"""
Phase 2: Delta sync API – apply only changed fields with updated_at conflict check.
Accepts POST { "items": [ { "entity_type", "id", "changes": {...}, "updated_at" } ] }.
Used by sync-manager when sending diffs from the local mirror.
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.siteconfig.models import SiteSettings


# Entity types we support for delta PATCH; map to (model, allowed_fields).
def _get_entity_config():
    from apps.people.models import StudentProfile
    from apps.academics.models import Attendance, Classroom

    return {
        "student": (StudentProfile, {"first_name", "last_name", "student_code", "classroom_id", "academic_year_id", "specialty_id", "status", "is_active"}),
        "attendance": (Attendance, {"student_id", "classroom_id", "date", "status", "remarks"}),
        "classroom": (Classroom, {"name", "academic_year_id", "is_active"}),
    }


def _parse_client_updated_at(raw):
    if not raw:
        return None
    if hasattr(raw, "isoformat"):
        return timezone.make_aware(raw, timezone.get_current_timezone()) if timezone.is_naive(raw) else raw
    parsed = parse_datetime(str(raw))
    if not parsed:
        return None
    return timezone.make_aware(parsed, timezone.get_current_timezone()) if timezone.is_naive(parsed) else parsed


def _user_can_edit_entity(request, entity_type, instance):
    """Return True if request.user can edit this entity (same rules as entity/attendance APIs)."""
    from apps.api.entity_api import _is_admin_like
    user = request.user
    if user.is_superuser or user.is_staff:
        return True
    if entity_type == "student":
        return _is_admin_like(user)
    if entity_type == "attendance":
        if _is_admin_like(user):
            return True
        from apps.evals.models import TeacherAssignment
        teacher = getattr(user, "teacher_profile", None)
        if not teacher:
            return False
        classroom_ids = set(
            TeacherAssignment.objects.filter(teacher=teacher, is_active=True)
            .values_list("subject_assignment__classroom_id", flat=True)
        )
        return getattr(instance, "classroom_id", None) in classroom_ids
    if entity_type == "classroom":
        return _is_admin_like(user)
    return False


def _apply_delta_item(request, entity_type, pk, changes, client_updated_at):
    """Apply only `changes` to the entity; return (success, response_or_none)."""
    config = _get_entity_config()
    if entity_type not in config:
        return False, Response({"error": f"Unknown entity_type: {entity_type}"}, status=status.HTTP_400_BAD_REQUEST)
    model, allowed = config[entity_type]
    if not isinstance(changes, dict):
        return False, Response({"error": "changes must be an object"}, status=status.HTTP_400_BAD_REQUEST)
    updates = {k: v for k, v in changes.items() if k in allowed}
    if not updates:
        return False, Response({"error": "No allowed fields to update"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return False, Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    if not _user_can_edit_entity(request, entity_type, instance):
        return False, Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
    school = getattr(request, "school", None)
    if school and hasattr(instance, "school_id") and instance.school_id != school.id:
        return False, Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
    server_dt = getattr(instance, "updated_at", None)
    if client_updated_at and server_dt:
        if timezone.is_naive(server_dt):
            server_dt = timezone.make_aware(server_dt, timezone.get_current_timezone())
        if client_updated_at < server_dt:
            return False, Response(
                {"error": "conflict", "server_updated_at": server_dt.isoformat()},
                status=status.HTTP_409_CONFLICT,
            )
    for key, value in updates.items():
        setattr(instance, key, value)
    instance.save(update_fields=list(updates.keys()) + ["updated_at"] if hasattr(instance, "updated_at") else list(updates.keys()))
    return True, Response({"id": instance.pk, "updated_at": getattr(instance, "updated_at", None).isoformat() if getattr(instance, "updated_at", None) else None}, status=status.HTTP_200_OK)


class DeltaSyncAPI(APIView):
    """
    POST body: { "items": [ { "entity_type": "student", "id": 1, "changes": { "first_name": "X" }, "updated_at": "2025-01-01T12:00:00Z" } ] }
    Returns: { "results": [ { "index", "status", "data" } ], "removed_ids": [...], "failed_count", "failed_items" }.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        site = SiteSettings.get_solo()
        if not getattr(site, "enable_offline_mode", False):
            return Response({"error": "Offline sync is disabled."}, status=status.HTTP_403_FORBIDDEN)
        items = request.data.get("items") or []
        if not isinstance(items, list):
            return Response({"error": "items must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        if len(items) > 50:
            return Response({"error": "Maximum 50 items per delta batch"}, status=status.HTTP_400_BAD_REQUEST)
        results = []
        removed_ids = []
        failed_items = []
        for idx, item in enumerate(items):
            entity_type = (item.get("entity_type") or "").strip().lower()
            pk = item.get("id")
            changes = item.get("changes")
            client_updated_at = _parse_client_updated_at(item.get("updated_at"))
            item_id = item.get("client_item_id")
            if not entity_type or pk is None:
                results.append({"index": idx, "status": 400, "data": {"error": "entity_type and id required"}})
                if item_id is not None:
                    failed_items.append({"url": f"{entity_type}/{pk}", "status": 400, "message": "entity_type and id required"})
                continue
            ok, resp = _apply_delta_item(request, entity_type, pk, changes or {}, client_updated_at)
            status_code = resp.status_code
            try:
                data = resp.data
            except Exception:
                data = {"_status": status_code}
            results.append({"index": idx, "status": status_code, "data": data})
            if ok and item_id is not None:
                removed_ids.append(item_id)
            elif status_code >= 400 and item_id is not None:
                msg = (data.get("error") or data.get("message") or f"HTTP {status_code}")
                failed_items.append({"url": f"{entity_type}/{pk}", "status": status_code, "message": str(msg)})
        return Response({
            "results": results,
            "removed_ids": removed_ids,
            "failed_count": len(failed_items),
            "failed_items": failed_items,
        })
