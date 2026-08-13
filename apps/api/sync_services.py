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
        # NOTE: no "is_active" — Classroom has no such field. Leaving the phantom in
        # would crash the UPDATE path (`save(update_fields=["is_active"])` → FieldError)
        # whenever a classroom edit carried it.
        "classroom": (Classroom, {"name", "academic_year_id"}),
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


def apply_changes(school_id, user, items, *, persist_conflicts=True, sync_origin=None):
    """Sentry-traced wrapper. Backs the `sync.conflict_pending` SLO.

    ``sync_origin`` (e.g. ``"cloud-pull"`` / ``"edge-push"``) marks that these writes
    are part of edge<->cloud SYNC, not a local user edit — each applied row then records
    an echo-suppression provenance marker so the reverse delta never ships it back
    (see apps.sync_engine.models.SyncApplyLedger). ``None`` (the online DeltaSyncAPI
    default) records nothing, so a genuine local edit still propagates.
    """
    from apps.observability.tracing import (
        finish_transaction, set_transaction_status, start_named_transaction,
    )

    _txn = start_named_transaction(
        "sync.delta_apply", op="task.hot_path",
        school_id=str(school_id) if school_id else "",
        item_count=len(items) if items else 0,
    )
    try:
        return _apply_changes_inner(
            school_id, user, items, persist_conflicts=persist_conflicts, sync_origin=sync_origin
        )
    except Exception:
        set_transaction_status(_txn, "internal_error")
        raise
    finally:
        finish_transaction(_txn)


def _apply_changes_inner(school_id, user, items, *, persist_conflicts=True, sync_origin=None):
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
            if sync_origin:
                # Provenance marker so the reverse delta won't echo this sync-applied row.
                from apps.sync_engine.models import record_sync_apply

                record_sync_apply(school_id, entity_type, instance.pk, new_updated_at, sync_origin)
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


# Foreign-key fields (in the entity allow-lists) that reference another synced entity.
# Used to REMAP a link that points at ANOTHER insert-row (its box-local pk differs from
# the operator pk) onto the referent's freshly-assigned operator pk once it exists.
_INSERT_FK_TARGET = {"student_id": "student", "classroom_id": "classroom"}


def _insert_dependency_order(config) -> list:
    """Order the entity types so a new row that references ANOTHER new row is created
    AFTER its referent (whose operator pk we then substitute for the box's local pk).

    The edge graph is ``_INSERT_FK_TARGET``: an entity depends on another when one of its
    allowed fields is a FK to that other entity (e.g. ``attendance.student_id`` -> student,
    ``student.classroom_id`` -> classroom). A Kahn-style topological sort with a
    deterministic (sorted) tie-break; a cycle (none exist today) degrades gracefully to
    sorted order — those rows simply fall back to FK-drop, never mis-link.
    """
    deps: dict[str, set] = {}
    for entity_type, (_model, allowed) in config.items():
        needed = set()
        for field in allowed:
            target = _INSERT_FK_TARGET.get(field)
            if target and target in config and target != entity_type:
                needed.add(target)
        deps[entity_type] = needed

    order: list = []
    placed: set = set()
    while len(placed) < len(deps):
        ready = sorted(et for et in deps if et not in placed and deps[et] <= placed)
        if not ready:  # cycle guard — deterministic fallback, never an infinite loop
            ready = sorted(et for et in deps if et not in placed)
        for et in ready:
            order.append(et)
            placed.add(et)
    return order


def _settable_field_names(model) -> set:
    """Concrete field names on ``model`` that can be passed to ``create`` — includes
    both the relation name and its ``<field>_id`` attname. Lets the insert path ignore
    any phantom entry in an allow-list (e.g. a field that doesn't exist on the model)."""
    names: set = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if getattr(f, "name", None):
            names.add(f.name)
        attname = getattr(f, "attname", None)
        if attname:
            names.add(attname)
    return names


def apply_edge_inserts(school_id, user, rows, *, sync_origin=None):
    """Upsert offline-CREATED rows by ``(school, client_offline_id)`` — edge-only.

    The counterpart to :func:`apply_changes` (which is update-by-pk). Rows here were
    created on an edge box and carry a client-generated ``client_offline_id`` plus the
    box's LOCAL integer pks, which are meaningless on the operator — so we NEVER look
    up by pk; we upsert by ``(school, client_offline_id)`` under a per-row savepoint so
    one bad row never rolls back the batch. Only an admin-like / staff / superuser may
    create (the edge box acts as a bound school admin).

    **FK id-remapping (new-references-new).** A foreign key that points at ANOTHER
    insert-row's box-local pk cannot be applied verbatim (the operator assigns its own
    pk). Rows are therefore processed in dependency order (:func:`_insert_dependency_order`
    — referents before dependents), and each new row's freshly-assigned operator pk is
    recorded in a ``(entity_type, local_pk) -> operator_pk`` map; a dependent FK is then
    REMAPPED onto that operator pk. If the referent could not be created (or isn't in the
    bundle), the FK is dropped — the dependent row then links only to already-present
    (cloned, pk-stable) records or, if that FK was required, fails cleanly and is reported,
    never silently mis-linked. Results are returned in the caller's ORIGINAL row order
    regardless of the internal processing order.

    Returns ``{"created", "updated", "results"}`` (results carry per-row index/status).
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import DataError, IntegrityError, transaction

    from apps.api.entity_api import _is_admin_like
    from apps.schools.models import School

    config = _get_entity_config()
    school = School.objects.filter(pk=school_id).first() if school_id else None
    can_create = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or _is_admin_like(user)
    )

    # Local pks that belong to NEW (insert) rows, keyed by entity — their operator pk
    # will differ, so a FK pointing at one of them must be remapped, never applied raw.
    new_local_pks: dict[str, set] = {}
    for item in rows:
        et = (item.get("entity_type") or "").strip().lower()
        pid = item.get("id")
        if et and pid is not None:
            new_local_pks.setdefault(et, set()).add(pid)

    created = 0
    updated = 0
    if school is None or not can_create:
        reason = "tenant_context_required" if school is None else "forbidden"
        return {
            "created": 0,
            "updated": 0,
            "results": [{"index": i, "status": 403, "data": {"error": reason}} for i, _ in enumerate(rows)],
        }

    # (entity_type, box-local pk) -> assigned operator pk, filled as referents are created
    # so a later dependent row can substitute the real pk for the box's local one.
    remap: dict[tuple, object] = {}
    order = _insert_dependency_order(config)

    def _rank(item):
        et = (item.get("entity_type") or "").strip().lower()
        return order.index(et) if et in order else len(order)

    # Process referents before dependents; stable by original index within a rank. Results
    # are stored by original index and emitted in original order below.
    ordered = sorted(enumerate(rows), key=lambda pair: (_rank(pair[1]), pair[0]))
    results_by_index: dict[int, dict] = {}

    for idx, item in ordered:
        entity_type = (item.get("entity_type") or "").strip().lower()
        coid = (item.get("client_offline_id") or "").strip()
        local_pk = item.get("id")
        changes = item.get("changes") or {}
        if entity_type not in config or not coid:
            results_by_index[idx] = {"index": idx, "status": 400, "data": {"error": "entity_type_and_client_offline_id_required"}}
            continue
        model, allowed = config[entity_type]
        if not any(getattr(f, "name", "") == "client_offline_id" for f in model._meta.get_fields()):
            results_by_index[idx] = {"index": idx, "status": 422, "data": {"error": "entity_not_insertable"}}
            continue

        valid_fields = _settable_field_names(model)
        updates = {}
        dropped_fks = []
        for key, value in changes.items():
            if key not in allowed or key not in valid_fields:
                continue  # not editable, or a phantom allow-list entry not on the model
            target = _INSERT_FK_TARGET.get(key)
            if target and value in new_local_pks.get(target, set()):
                # Points at another new row: substitute the referent's operator pk if it
                # was already created this batch, else DROP (a required FK then fails
                # cleanly; a nullable FK lands NULL — surfaced via dropped_fks so the
                # caller can reconcile rather than treat a partial row as a clean success).
                remapped = remap.get((target, value))
                if remapped is None:
                    dropped_fks.append(key)
                    continue
                value = remapped
            updates[key] = value

        try:
            with transaction.atomic():  # savepoint: isolate a bad row from the batch
                obj, was_created = model.objects.get_or_create(
                    school=school, client_offline_id=coid, defaults=updates
                )
                if not was_created and updates:
                    for key, value in updates.items():
                        setattr(obj, key, value)
                    obj.save(update_fields=list(updates.keys()))
        except (IntegrityError, DataError, ValidationError, ValueError, TypeError, FieldError) as exc:
            # DataError (value too long / out of range on Postgres) is a DatabaseError
            # sibling of IntegrityError; catching it keeps the per-row savepoint from
            # escaping and rolling back the whole batch (SQLite doesn't enforce
            # max_length, so only prod Postgres exercised this path).
            results_by_index[idx] = {"index": idx, "status": 422, "data": {"error": "insert_failed", "detail": str(exc)[:200]}}
            continue

        # Record the operator pk so later dependent rows can remap their FK onto it.
        if local_pk is not None:
            remap[(entity_type, local_pk)] = obj.pk

        if was_created:
            created += 1
        else:
            updated += 1
        if sync_origin:
            # Provenance marker so the reverse delta won't echo this sync-applied insert.
            from apps.sync_engine.models import record_sync_apply

            record_sync_apply(
                school_id, entity_type, obj.pk, getattr(obj, "updated_at", None), sync_origin
            )
        data = {"id": obj.pk, "created": was_created}
        if dropped_fks:
            data["dropped_fks"] = dropped_fks  # links that pointed at an uncreated new row
        results_by_index[idx] = {"index": idx, "status": 201 if was_created else 200, "data": data}

    results = [results_by_index[i] for i in range(len(rows))]
    return {"created": created, "updated": updated, "results": results}
