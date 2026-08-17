"""
Phase G: Delta-Sync engine – apply only changed fields with updated_at conflict check.
When server has a newer version than client's base_timestamp, do not overwrite;
create a SyncConflict record and return it in results for Sync Center resolution.

Frontend MUST use tenant-scoped cache: IndexedDB key e.g. sync_queue_${school_id}
so that no cross-tenant data is ever visible (one school per device/session).
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime


# CLASS-A master-data models wired with AUTO-DERIVED syncable fields (Phase 3, staged
# to full coverage). Each MUST already carry both a ``client_offline_id`` anchor and an
# ``auto_now`` ``updated_at`` (so identity is stable across deployments and the delta
# cursor works) — verified before adding. Later slices append rows here (adding the
# anchor/timestamp schema first for models that lack it).
_DERIVED_ENTITY_SPECS: list[tuple[str, str, str]] = [
    ("applicant", "people", "Applicant"),
    ("student_note", "people", "StudentNote"),
    # Slice 2 — academic backbone (client_offline_id + updated_at added by migration).
    # term.academic_year_id references academic_year (also registered), so the derived
    # per-entity remap graph links them for new-references-new inserts.
    ("academic_year", "academics", "AcademicYear"),
    ("term", "academics", "Term"),
    ("department", "academics", "Department"),
    # Slice 3 — curriculum catalog (edge parity, 2026-08-16). Benign master data the
    # box needs to mirror the cloud: subjects, specialties (trades), and the
    # specialty↔subject curriculum links. Anchor (client_offline_id + updated_at)
    # added by academics migration 0080. FK remap: specialty.department_id →
    # department, and specialty_subject.{specialty,subject}_id → the entities below
    # (all registered), so a new-references-new insert resolves onto operator pks.
    ("specialty", "academics", "Specialty"),
    ("subject", "academics", "Subject"),
    ("specialty_subject", "academics", "SpecialtySubject"),
    # Slice 4 — the teaching grid (edge parity, 2026-08-17). SubjectAssignment is the
    # join the box needs so a term's gradeable slots exist offline: academic_year + term
    # + classroom + specialty + subject (+ coefficient). Anchor added by academics
    # migration 0081. All five FKs point at entities registered ABOVE, so a
    # new-references-new insert remaps cleanly onto the operator's pks.
    # NOTE: the `teachers` M2M does NOT ride — it targets the SHARED accounts.User,
    # whose pk is not portable box↔cloud (the same reason a FK to User is excluded), and
    # an M2M cannot appear in `save(update_fields=...)`. `_derive_sync_fields` drops it.
    ("subject_assignment", "academics", "SubjectAssignment"),
    # Slice 5 — grades, DOWN-ONLY (edge parity, 2026-08-17). evals.Evaluation is the mark
    # row. It is deliberately NOT in _LWW_SAFE_ENTITIES: `evaluation` aliases to the
    # protected `grade_entry` policy, so _conflict_decision applies it on a cloud-pull and
    # raises a Sync Center CONFLICT for a box push — a box can never silently overwrite a
    # mark the cloud holds. Anchor added by evals migration 0039 (it already had
    # updated_at). Its subject_assignment_id resolves onto the entity registered directly
    # above, which is why the teaching grid had to land first; student_id resolves onto
    # `student`. created_by/updated_by are FKs to the SHARED accounts.User and are dropped
    # automatically as non-portable.
    ("evaluation", "evals", "Evaluation"),
    # DEFERRED — people.TeacherProfile is CLASS-A master data but carries compensation
    # fields (salary_amount, pay_grade, next_pay_date, …). Two-way LWW on those would let
    # a box salary edit override the cloud, against the money=cloud-authoritative rule.
    # It joins once Phase 4 gives per-field direction policy (compensation = down-only).
]

# Field names never synced as a value: the tenant scope, the identity anchor, and the
# auto timestamps (handled by the engine, not carried as data).
_SYNC_FIELD_EXCLUDE_NAMES = {"school", "client_offline_id", "created_at", "updated_at"}

# Per-entity fields REMOVED from the auto-derived sync set. These are ordinary editable
# scalars, but they are cloud-governance columns that must NOT converge by two-way LWW —
# a stale offline box edit must never silently override the cloud's value. Until per-field
# direction policy exists (the same gap that defers TeacherProfile compensation), the safe
# move is to keep them OFF the sync rail entirely:
#   * academic_year.is_locked / enable_gce_registration — the year-end lock and the exam-
#     registration gate (MEMORY M29). A box must never be able to reopen a year the cloud
#     locked; the cloud owns these. (The academic_year still syncs its benign fields.)
_SYNC_FIELD_EXCLUDE_PER_ENTITY: dict[str, set] = {
    "academic_year": {"is_locked", "enable_gce_registration"},
}

# Per-FIELD direction policy: columns that ride DOWN (cloud→box) but are NEVER accepted
# UPWARD, on an entity that is otherwise benign two-way LWW. `_conflict_decision` grades a
# whole ENTITY, so a single cloud-governed column previously had only two bad options —
# leave the entity two-way (a stale box can move it) or drop the column off the rail
# entirely (the box never receives it, so it cannot compute correctly offline). This gives
# the third, correct option: the box RECEIVES the cloud's value, and an upward write to it
# is refused and REPORTED rather than silently discarded.
#   * subject_assignment.coefficient — the per-subject weight that multiplies a mark into
#     the term average and the report card. Marks themselves are down-only (the protected
#     grade_entry policy), so letting a stale box overwrite the WEIGHT would move every
#     computed average by the back door while each individual mark stayed authoritative.
#     The box still needs the value to grade offline, so excluding it is not an option.
# A field listed here must also be in the entity's synced set — it is a direction rule,
# not an exclusion. When per-field direction policy grows up (the same Phase 4 gap that
# defers TeacherProfile compensation), this map is what it generalizes.
_DOWN_ONLY_FIELDS_PER_ENTITY: dict[str, set] = {
    "subject_assignment": {"coefficient"},
}

# Registered entities that are SAFE to converge by last-writer-wins and are NOT already
# classified in policy_registry.POLICIES. Kept EXPLICIT (not derived from the registry) so
# that adding a new entity to _DERIVED_ENTITY_SPECS without consciously listing it here —
# or giving it a POLICIES entry — makes _sync_conflict_policy fail CLOSED (protected
# manual review) rather than silently treating a possibly-sensitive entity as two-way LWW.
# When you add a benign master-data entity, add it here; a money/grade/identity entity must
# instead get a protected POLICIES row.
_LWW_SAFE_ENTITIES = frozenset(
    {
        "student", "classroom", "applicant", "academic_year", "term", "department",
        # Curriculum catalog (Slice 3): benign master data, safe to converge by
        # timestamp — a later admin edit wins, same as the other master-data rows.
        "specialty", "subject", "specialty_subject",
        # Teaching grid (Slice 4): benign master data — WHICH gradeable slots exist for a
        # term. It carries no marks (an Evaluation points AT a slot; grades ride their own
        # down-only rail), so a later admin edit winning is correct.
        "subject_assignment",
    }
)


def _is_sync_tenant_model(model) -> bool:
    """True if ``model`` lives in a tenant app — so its pk is stable across the
    pk-preserving clone (or remappable when it is itself a synced entity). A FK to a
    SHARED/public model (e.g. ``accounts.User``) is NOT: its id differs box vs cloud, so
    such a link is never synced as a field."""
    if model is None:
        return False
    from apps.lifecycle.tenant_portability import TENANT_APP_LABELS

    return model._meta.app_label in TENANT_APP_LABELS


def _derive_sync_fields(model) -> set:
    """The syncable field set for a CLASS-A model: every editable concrete scalar plus
    FKs that point at a TENANT model (pk-stable / remappable). Excludes the pk, the
    tenant scope, the anchor, auto timestamps, and any FK to a shared/public model."""
    fields: set = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False) or getattr(f, "primary_key", False):
            continue
        if getattr(f, "auto_created", False) or not getattr(f, "editable", True):
            continue
        if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
            continue
        if f.name in _SYNC_FIELD_EXCLUDE_NAMES:
            continue
        # MANY-TO-MANY IS NEVER A SYNCED FIELD. Django reports an M2M as concrete+editable,
        # so without this guard it lands in the set and breaks BOTH directions: the outbox
        # does ``getattr(instance, f)`` per allowed field, which for an M2M yields a
        # ManyRelatedManager that ``export_delta_bundle`` cannot JSON-serialize — and
        # because a bundle packs EVERY registered entity into ONE payload, that single bad
        # column takes down the whole push/pull cycle, not just its own entity. On the
        # inbound side an M2M cannot appear in ``save(update_fields=[...])`` either
        # (FieldError — the same phantom-field crash the curated ``classroom`` set warns
        # about above). A through-table link is its own relation and, when one is genuinely
        # needed on the rail, must be registered as its own entity with its own anchor.
        if getattr(f, "many_to_many", False):
            continue
        # A FileField/ImageField NEVER rides either. A delta bundle carries column VALUES
        # only — never file bytes — so shipping the stored path would point the box at a
        # file that does not exist on it, and the apply would report a clean 200 over a
        # broken reference. Files must travel by their own upload/artifact channel. This is
        # latent today (only `student` owns one, and it keeps a CURATED field set) but every
        # finance candidate — Invoice.attachment/payment_proof, Payment.receipt_file,
        # PaymentProofUpload.receipt_file — would hit it the moment money joins the rail.
        from django.db.models import FileField

        if isinstance(f, FileField):
            continue
        if getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False):
            # Resolve a possibly lazy-string related_model to its class first (same guard
            # tenant_portability._rel_model adds) so a string ref never AttributeErrors here.
            from apps.lifecycle.tenant_portability import _rel_model

            if not _is_sync_tenant_model(_rel_model(f)):
                continue  # FK to User/other shared model — id not portable across deployments
            fields.add(f.attname)  # sync the <name>_id
        else:
            fields.add(f.name)
    return fields


def _get_entity_config(include_derived=False):
    from apps.people.models import StudentProfile
    from apps.academics.models import Attendance, Classroom
    from django.apps import apps as django_apps

    # The original three entities keep their CURATED field sets verbatim, so their
    # long-tested sync behaviour is unchanged by the generalized registry.
    config = {
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
    # The expanded two-way registry is scoped to EDGE SYNC operations only — callers on
    # the edge push/pull paths pass include_derived=True. An ordinary online DeltaSyncAPI
    # request (sync_origin is None) NEVER includes them, so every other tenant, on ANY
    # deployment (including a shared cloud that also serves edge boxes), sees exactly the
    # original three entities. Isolation therefore does not depend on a deployment-global
    # switch — an unregistered/derived entity from a non-edge caller is simply rejected.
    if include_derived:
        for entity_type, app_label, model_name in _DERIVED_ENTITY_SPECS:
            try:
                model = django_apps.get_model(app_label, model_name)
            except LookupError:
                continue
            fields = _derive_sync_fields(model) - _SYNC_FIELD_EXCLUDE_PER_ENTITY.get(
                entity_type, set()
            )
            config[entity_type] = (model, fields)
    return config


def _insert_fk_targets(config) -> dict:
    """``{entity_type: {fk_attname: target_entity_type}}`` for FKs (in each entity's
    synced field set) that point at ANOTHER registered entity — so a new-references-new
    insert can be remapped onto the referent's operator pk. Derived PER ENTITY, so a
    field name that resolves to different targets on different models (e.g.
    ``merged_into_id`` on student vs teacher) is never conflated by a global map."""
    model_to_entity = {model: et for et, (model, _f) in config.items()}
    targets: dict = {}
    for et, (model, allowed) in config.items():
        per_entity: dict = {}
        for f in model._meta.get_fields():
            if not (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
                continue
            if not getattr(f, "concrete", False):
                continue
            attname = getattr(f, "attname", None)
            if attname not in allowed:
                continue
            from apps.lifecycle.tenant_portability import _rel_model

            target_et = model_to_entity.get(_rel_model(f))
            if target_et and target_et != et:
                per_entity[attname] = target_et
        targets[et] = per_entity
    return targets


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
    # Generalized CLASS-A master data (teacher, applicant, student_note, …): an
    # admin-like principal manages it. The edge sync principal is the school
    # owner/superuser, already allowed above; this also lets a tenant admin edit it
    # online. Unknown entity types still fall through to a hard deny.
    if entity_type in {spec[0] for spec in _DERIVED_ENTITY_SPECS}:
        return _is_admin_like(user)
    return False


def _sync_conflict_policy(entity_type):
    """``(strategy, protected)`` governing an entity's sync conflicts.

    A registered two-way entity with no explicit ``policy_registry`` entry is treated as
    LWW master data (it was deliberately chosen as safe to converge by timestamp). An
    entity the registry KNOWS — money (fee_payment / invoice_line / payment_proof),
    grades (grade_entry), identity (user_profile / permission_grant), etc. — keeps its
    declared, protected strategy. Aliases are normalized (attendance→attendance_record).
    """
    from apps.sync_engine.policy_registry import (
        MergeStrategy, POLICIES, get_policy, normalize_entity,
    )

    norm = normalize_entity(entity_type)
    if norm in POLICIES:
        p = get_policy(entity_type)
        return p.strategy, p.protected
    if norm in _LWW_SAFE_ENTITIES or entity_type in _LWW_SAFE_ENTITIES:
        return MergeStrategy.CAUSAL_LWW, False
    # Fail CLOSED for anything not explicitly classified — mirrors policy_registry's own
    # "unknown entities fail closed to protected manual review" default, so a sensitive
    # entity can never silently become two-way LWW.
    p = get_policy(entity_type)
    return p.strategy, p.protected


def _conflict_decision(entity_type, sync_origin, client_updated_at, server_dt):
    """Decide how to apply one delta row: ``"apply"`` | ``"conflict"`` | ``"reject"``.

    * LWW master data — newest ``updated_at`` wins; a provably older incoming change is a
      conflict (the local, newer record is kept).
    * Protected / authoritative (money, grades, identity) — the CLOUD is the source of
      truth. A ``cloud-pull`` (cloud→box) always wins on the box (``apply``); a box→cloud
      push or an online edit NEVER silently overwrites it (``conflict`` → Sync Center).
      This is the money = cloud-authoritative rule, enforced by policy not by entity name.
    * ``ONLINE_REQUIRED`` domains (credentials, lifecycle, settlement) are never applied
      through the offline/sync path (``reject``).
    """
    from apps.sync_engine.policy_registry import MergeStrategy

    strategy, protected = _sync_conflict_policy(entity_type)
    if strategy == MergeStrategy.ONLINE_REQUIRED:
        return "reject"
    if protected:
        return "apply" if sync_origin == "cloud-pull" else "conflict"
    # LWW: newest wins. A client row that cannot PROVE it is newer — a missing or
    # unparseable updated_at (client_updated_at is None) — must not silently overwrite a
    # server row that HAS a timestamp; treat it as a conflict for a human to resolve.
    # Both-missing (a brand-new row with no server-side timestamp to beat) still applies.
    if client_updated_at is None:
        return "conflict" if server_dt is not None else "apply"
    if server_dt is not None and client_updated_at < server_dt:
        return "conflict"
    return "apply"


def _serialize_instance_for_conflict(instance, entity_type, fields_subset):
    """Build server_data snapshot for conflict record (only allowed/relevant fields).

    Every value MUST survive ``json.dumps``: the snapshot lands in a JSONField, and if it
    cannot be encoded the CONFLICT RECORD ITSELF fails to save. That failure mode is worse
    than it looks — the row is then neither applied nor reviewable (it returns
    ``conflict_persist_failed`` instead of a 409 with a ``conflict_id``), which silently
    defeats MANUAL_REVIEW for exactly the protected entities that depend on it. ``Decimal``
    is the offender: a grade or money snapshot is full of them. Decimals are stringified,
    matching how the delta wire already ships them (``json.dumps(default=str)``), and a
    final encodability probe catches any other exotic type rather than letting one field
    lose a whole conflict.
    """
    import json
    from decimal import Decimal

    data = {}
    for f in fields_subset:
        if hasattr(instance, f):
            v = getattr(instance, f)
            if hasattr(v, "pk"):
                data[f] = v.pk
            elif hasattr(v, "isoformat"):
                data[f] = v.isoformat() if v else None
            elif isinstance(v, Decimal):
                data[f] = str(v)
            else:
                try:
                    json.dumps(v)
                    data[f] = v
                except (TypeError, ValueError):
                    data[f] = str(v)
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
    from django.core.exceptions import FieldError, ValidationError
    from django.db import DataError, IntegrityError, transaction

    # Edge sync operations (sync_origin set) get the expanded registry; an online
    # DeltaSyncAPI call (sync_origin None) gets only the original three — other tenants
    # untouched.
    config = _get_entity_config(include_derived=sync_origin is not None)
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
            if server_dt is not None and timezone.is_naive(server_dt):
                server_dt = timezone.make_aware(server_dt, timezone.get_current_timezone())

            decision = _conflict_decision(entity_type, sync_origin, client_updated_at, server_dt)
            if decision == "reject":
                # Domain may only change through a live online transaction (policy
                # ONLINE_REQUIRED); an offline/sync replay must never apply it.
                results.append(
                    {
                        "index": idx,
                        "status": 409,
                        "data": {"error": "online_required", "entity_type": entity_type},
                    }
                )
                continue
            if decision == "conflict":
                # Do not overwrite; persist SyncConflict for Sync Center resolution. Fires
                # on a stale LWW change OR any box/online change to a cloud-authoritative
                # (protected) record — the cloud's copy is kept until a human decides.
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
                        try:
                            # Savepoint: persisting the conflict record must not be able to
                            # abort the whole batch. (Also degrades gracefully if a future
                            # UUID-pk entity is registered before SyncConflict.entity_id is
                            # widened — a DataError here becomes a 422, never a batch 500.)
                            with transaction.atomic():
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
                        except (
                            IntegrityError, DataError, ValidationError,
                            ValueError, TypeError, FieldError,
                        ) as exc:
                            results.append({
                                "index": idx, "status": 422,
                                "data": {"error": "conflict_persist_failed", "detail": str(exc)[:200]},
                            })
                            continue
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
                        "server_updated_at": server_dt.isoformat() if server_dt else None,
                        "conflict_id": conflict_id,
                    }
                )
                results.append(
                    {
                        "index": idx,
                        "status": 409,
                        "data": {
                            "error": "conflict",
                            "server_updated_at": server_dt.isoformat() if server_dt else None,
                            "conflict_id": conflict_id,
                        },
                        "conflict_id": conflict_id,
                    }
                )
                continue

            # Per-FIELD direction guard (see _DOWN_ONLY_FIELDS_PER_ENTITY). The entity-level
            # decision above already said "apply", but a cloud-governed column must still not
            # travel upward. Strip it from a box push / online edit and REPORT the refusal, so
            # a discarded write is visible instead of vanishing.
            rejected_down_only = []
            if sync_origin != "cloud-pull":
                for _f in sorted(_DOWN_ONLY_FIELDS_PER_ENTITY.get(entity_type, ())):
                    if _f in updates:
                        updates.pop(_f)
                        rejected_down_only.append(_f)
            if rejected_down_only and not updates:
                # The row carried nothing BUT down-only fields: refuse it outright rather than
                # bumping updated_at for a write that changed nothing (which would also re-ship
                # the row on the next delta).
                results.append({
                    "index": idx,
                    "status": 409,
                    "data": {
                        "error": "down_only_fields_rejected",
                        "fields": rejected_down_only,
                    },
                })
                continue

            try:
                # Apply updates INSIDE the per-row guard. A bad value raises at ASSIGNMENT
                # time, before any save — a non-assignable descriptor raises TypeError, a
                # malformed value ValueError/ValidationError. While this loop sat outside
                # the try, such a row escaped `apply_changes` altogether and killed the
                # WHOLE bundle apply (every entity in it, not just the offending row),
                # instead of degrading this ONE row to the 422 the handler below already
                # returns. Keep assignment and save under the same guard.
                for key, value in updates.items():
                    setattr(instance, key, value)
                update_fields = list(updates.keys())
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                # Per-row savepoint: one un-appliable row (FK to a deleted parent, a
                # unique/not-null collision — SQLite doesn't enforce these, only prod
                # Postgres does) must roll back ONLY this row, never the whole bundle. The
                # save + its echo-suppression ledger write are one atomic unit so a saved
                # row can never be left without provenance (which would re-ship it forever).
                with transaction.atomic():
                    instance.save(update_fields=update_fields)
                    new_updated_at = getattr(instance, "updated_at", None)
                    if sync_origin:
                        # Provenance marker so the reverse delta won't echo this apply.
                        from apps.sync_engine.models import record_sync_apply

                        record_sync_apply(
                            school_id, entity_type, instance.pk, new_updated_at, sync_origin
                        )
            except (
                IntegrityError, DataError, ValidationError,
                ValueError, TypeError, FieldError,
            ) as exc:
                results.append({
                    "index": idx, "status": 422,
                    "data": {"error": "apply_failed", "detail": str(exc)[:200]},
                })
                continue
            success_count += 1
            _data = {
                "id": instance.pk,
                "updated_at": new_updated_at.isoformat() if new_updated_at else None,
            }
            if rejected_down_only:
                # Partial acceptance: the benign fields landed, the cloud-governed ones did
                # not. Surfaced so the caller can reconcile rather than read a 200 as "all of
                # my changes were taken".
                _data["rejected_down_only_fields"] = rejected_down_only
            results.append({"index": idx, "status": 200, "data": _data})

    return {
        "success_count": success_count,
        "results": results,
        "conflicts": conflicts,
    }


def _insert_dependency_order(config) -> list:
    """Order the entity types so a new row that references ANOTHER new row is created
    AFTER its referent (whose operator pk we then substitute for the box's local pk).

    The edge graph is :func:`_insert_fk_targets` (derived per entity): an entity depends
    on another when one of its synced FK fields points at that other entity (e.g.
    ``attendance.student_id`` -> student, ``student.classroom_id`` -> classroom). A
    Kahn-style topological sort with a deterministic (sorted) tie-break; a cycle (e.g. a
    self-referential ``reports_to``) degrades gracefully to sorted order — those rows
    simply fall back to FK-drop, never mis-link.
    """
    fk_targets = _insert_fk_targets(config)
    deps: dict[str, set] = {}
    for entity_type in config:
        deps[entity_type] = {t for t in fk_targets.get(entity_type, {}).values() if t != entity_type}

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

    # Edge sync operations (sync_origin set) get the expanded registry; an online
    # DeltaSyncAPI call (sync_origin None) gets only the original three — other tenants
    # untouched.
    config = _get_entity_config(include_derived=sync_origin is not None)
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
    fk_targets = _insert_fk_targets(config)  # {entity_type: {fk_attname: target_entity_type}}

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
        ent_targets = fk_targets.get(entity_type, {})
        updates = {}
        dropped_fks = []
        for key, value in changes.items():
            if key not in allowed or key not in valid_fields:
                continue  # not editable, or a phantom allow-list entry not on the model
            target = ent_targets.get(key)
            if target and value is not None:
                if value in new_local_pks.get(target, set()):
                    # Points at another new row: substitute the referent's operator pk if it
                    # was already created this batch, else DROP (a required FK then fails
                    # cleanly; a nullable FK lands NULL — surfaced via dropped_fks so the
                    # caller can reconcile rather than treat a partial row as a clean success).
                    remapped = remap.get((target, value))
                    if remapped is None:
                        dropped_fks.append(key)
                        continue
                    value = remapped
                else:
                    # Points at an EXISTING (non-new) row of a registered entity: it MUST
                    # belong to THIS school. On the intended pk-preserving single-tenant
                    # clone it always does; a value that resolves to another tenant's row (a
                    # mis-provisioned box / stale reference) is DROPPED rather than linked
                    # cross-tenant. Guarantee #2 already holds (the created row is owned by
                    # `school`); this stops a wrong-but-in-schema link.
                    target_model = config[target][0]
                    if not target_model._default_manager.filter(pk=value, school=school).exists():
                        dropped_fks.append(key)
                        continue
            updates[key] = value

        try:
            with transaction.atomic():  # savepoint: isolate a bad row from the batch
                obj, was_created = model.objects.get_or_create(
                    school=school, client_offline_id=coid, defaults=updates
                )
                if not was_created and updates:
                    for key, value in updates.items():
                        setattr(obj, key, value)
                    update_fields = list(updates.keys())
                    if hasattr(obj, "updated_at"):
                        # Bump the change cursor, mirroring apply_changes — otherwise an
                        # UPDATE to an offline-created row keeps its old updated_at and is
                        # invisible to the incremental delta (filter(updated_at__gt=since)).
                        update_fields.append("updated_at")
                    obj.save(update_fields=update_fields)
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
