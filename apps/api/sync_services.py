"""
Phase G: Delta-Sync engine – apply only changed fields with updated_at conflict check.
When server has a newer version than client's base_timestamp, do not overwrite;
create a SyncConflict record and return it in results for Sync Center resolution.

Frontend MUST use tenant-scoped cache: IndexedDB key e.g. sync_queue_${school_id}
so that no cross-tenant data is ever visible (one school per device/session).
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _get_entity_config():
    from apps.people.models import StudentProfile
    from apps.academics.models import Attendance, Classroom

    return {
        "student": (
            StudentProfile,
            {
                "first_name",
                "last_name",
                "student_code",
                "classroom_id",
                "academic_year_id",
                "specialty_id",
                "status",
                "is_active",
            },
        ),
        "attendance": (
            Attendance,
            {"student_id", "classroom_id", "date", "status", "remarks"},
        ),
        "classroom": (Classroom, {"name", "academic_year_id", "is_active"}),
    }


def _parse_client_updated_at(raw):
    if not raw:
        return None
    if hasattr(raw, "isoformat"):
        return (
            timezone.make_aware(raw, timezone.get_current_timezone())
            if timezone.is_naive(raw)
            else raw
        )
    parsed = parse_datetime(str(raw))
    if not parsed:
        return None
    return (
        timezone.make_aware(parsed, timezone.get_current_timezone())
        if timezone.is_naive(parsed)
        else parsed
    )


def _user_can_edit_entity(user, entity_type, instance):
    from apps.api.entity_api import _is_admin_like

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
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("subject_assignment__classroom_id", flat=True)
        )
        return getattr(instance, "classroom_id", None) in classroom_ids
    if entity_type == "classroom":
        return _is_admin_like(user)
    return False


def _serialize_instance_for_conflict(instance, entity_type, fields_subset):
    """Build server_data snapshot for conflict record (only allowed/relevant fields)."""
    data = {}
    for f in fields_subset:
        if hasattr(instance, f):
            v = getattr(instance, f)
            if hasattr(v, "pk"):
                data[f] = v.pk
            elif hasattr(v, "isoformat"):
                data[f] = v.isoformat() if v else None
            else:
                data[f] = v
    return data


def apply_changes(school_id, user, items, *, persist_conflicts=True):
    """Sentry-traced wrapper. Backs the `sync.conflict_pending` SLO."""
    from apps.observability.tracing import (
        finish_transaction, set_transaction_status, start_named_transaction,
    )

    _txn = start_named_transaction(
        "sync.delta_apply", op="task.hot_path",
        school_id=str(school_id) if school_id else "",
        item_count=len(items) if items else 0,
    )
    try:
        return _apply_changes_inner(school_id, user, items, persist_conflicts=persist_conflicts)
    except Exception:
        set_transaction_status(_txn, "internal_error")
        raise
    finally:
        finish_transaction(_txn)


def _apply_changes_inner(school_id, user, items, *, persist_conflicts=True):
    """
    Apply delta items for the given tenant (school). Sort by client timestamp;
    for each item: if server record exists and server.updated_at > client_updated_at
    -> conflict: do not apply, optionally create SyncConflict and add to results.

    Returns:
        dict with:
          success_count: int
          results: list of { "index", "status", "data", "conflict_id" (if conflict persisted) }
          conflicts: list of { "index", "entity_type", "entity_id", "client_data", "server_data",
                              "client_updated_at", "server_updated_at", "conflict_id" }
    """
    from django.db import transaction

    config = _get_entity_config()
    results = []
    conflicts = []
    success_count = 0

    if not school_id:
        return {
            "success_count": 0,
            "results": [
                {
                    "index": idx,
                    "status": 403,
                    "data": {"error": "Tenant context required"},
                }
                for idx, _ in enumerate(items)
            ],
            "conflicts": [],
        }

    with transaction.atomic():
        for idx, item in enumerate(items):
            entity_type = (item.get("entity_type") or "").strip().lower()
            pk = item.get("id")
            changes = item.get("changes") or {}
            client_updated_at = _parse_client_updated_at(item.get("updated_at"))

            if entity_type not in config or pk is None:
                results.append(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "entity_type and id required"},
                    }
                )
                continue

            model, allowed = config[entity_type]
            if not isinstance(changes, dict):
                results.append(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "changes must be an object"},
                    }
                )
                continue
            updates = {k: v for k, v in changes.items() if k in allowed}
            if not updates:
                results.append(
                    {
                        "index": idx,
                        "status": 400,
                        "data": {"error": "No allowed fields to update"},
                    }
                )
                continue

            try:
                instance = model.objects.get(pk=pk)
            except model.DoesNotExist:
                results.append(
                    {"index": idx, "status": 404, "data": {"error": "Not found"}}
                )
                continue

            if not _user_can_edit_entity(user, entity_type, instance):
                results.append(
                    {"index": idx, "status": 403, "data": {"error": "Forbidden"}}
                )
                continue

            if hasattr(instance, "school_id"):
                instance_school_id = getattr(instance, "school_id", None)
                if instance_school_id is None or str(instance_school_id) != str(
                    school_id
                ):
                    results.append(
                        {"index": idx, "status": 403, "data": {"error": "Forbidden"}}
                    )
                    continue

            server_dt = getattr(instance, "updated_at", None)
            if client_updated_at and server_dt:
                if timezone.is_naive(server_dt):
                    server_dt = timezone.make_aware(
                        server_dt, timezone.get_current_timezone()
                    )
                if client_updated_at < server_dt:
                    # Conflict: do not overwrite; persist SyncConflict and return
                    server_data = _serialize_instance_for_conflict(
                        instance, entity_type, allowed
                    )
                    conflict_id = None
                    if persist_conflicts:
                        from apps.siteconfig.models import SyncConflict
                        from apps.schools.models import School

                        school = (
                            School.objects.filter(pk=school_id).first()
                            if school_id
                            else None
                        )
                        if school:
                            sc = SyncConflict.objects.create(
                                school=school,
                                entity_type=entity_type,
                                entity_id=pk,
                                client_data=dict(changes),
                                server_data=server_data,
                                client_updated_at=client_updated_at,
                                server_updated_at=server_dt,
                                reported_by=user,
                                status=SyncConflict.Status.PENDING,
                            )
                            conflict_id = sc.pk
                    conflicts.append(
                        {
                            "index": idx,
                            "entity_type": entity_type,
                            "entity_id": pk,
                            "client_data": dict(changes),
                            "server_data": server_data,
                            "client_updated_at": client_updated_at.isoformat()
                            if client_updated_at
                            else None,
                            "server_updated_at": server_dt.isoformat()
                            if server_dt
                            else None,
                            "conflict_id": conflict_id,
                        }
                    )
                    results.append(
                        {
                            "index": idx,
                            "status": 409,
                            "data": {
                                "error": "conflict",
                                "server_updated_at": server_dt.isoformat(),
                                "conflict_id": conflict_id,
                            },
                            "conflict_id": conflict_id,
                        }
                    )
                    continue

            # Apply updates
            for key, value in updates.items():
                setattr(instance, key, value)
            update_fields = list(updates.keys())
            if hasattr(instance, "updated_at"):
                update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
            success_count += 1
            new_updated_at = getattr(instance, "updated_at", None)
            results.append(
                {
                    "index": idx,
                    "status": 200,
                    "data": {
                        "id": instance.pk,
                        "updated_at": new_updated_at.isoformat()
                        if new_updated_at
                        else None,
                    },
                }
            )

    return {
        "success_count": success_count,
        "results": results,
        "conflicts": conflicts,
    }
