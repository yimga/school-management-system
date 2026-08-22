"""Record-merge engine (Wave C, design D6).

Re-parents every inbound FK/OneToOne row from the secondary person row onto
the primary via a SELF-MAINTAINING walker over the app registry (the purge
inventory proved the technique in production — a curated FK list drifts the
day a new FK lands). Unique-constraint collisions QUARANTINE: the colliding
row stays attached to the retired secondary and is listed on the operation
for operator review — never deleted, never silently skipped. The secondary
soft-retires (``is_active=False`` + ``merged_into`` tombstone where the
model carries one).

Deliberately out of scope (documented, not silent): GenericForeignKey
references (audit/history rows that name the secondary by string id remain
truthful history) and rows already pointing at BOTH sides of a uniqueness
boundary — those are the quarantine set.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MERGE_COMPUTATION = "people.merge"

_KIND_MODELS = {
    "student": ("people", "StudentProfile"),
    "teacher": ("people", "TeacherProfile"),
    "guardian": ("people", "StudentGuardian"),
}


class MergeBlockedError(RuntimeError):
    """A guard refused the merge — the operation FSM was NOT advanced."""


def person_model_for(kind: str):
    try:
        app_label, model_name = _KIND_MODELS[kind]
    except KeyError as exc:
        raise MergeBlockedError(f"unknown merge kind {kind!r}") from exc
    return django_apps.get_model(app_label, model_name)


_MISSING = object()

# How to reach the owning school from a person row, per merge kind. Stated
# explicitly because the three kinds are NOT the same shape: StudentProfile
# and TeacherProfile carry a school FK, while StudentGuardian is a link row
# scoped only through its student. A soft `getattr(row, "school_id", None)`
# therefore answered None for every guardian row, which the same-school guard
# read as "nothing to check" -- so it never fired for that kind.
_KIND_SCHOOL_PATHS: dict[str, tuple[str, ...]] = {
    "student": ("school_id",),
    "teacher": ("school_id",),
    "guardian": ("student", "school_id"),
}


def row_school_id(kind: str, row) -> Any:
    """The id of the school owning ``row``, or refuse.

    Never returns ``None`` for an unresolvable row: a guard that cannot
    determine the school must block the merge, not wave it through. If a new
    kind is added to ``_KIND_MODELS`` without a path here, every merge of that
    kind is refused until someone states where its school lives.
    """
    try:
        path = _KIND_SCHOOL_PATHS[kind]
    except KeyError as exc:
        raise MergeBlockedError(
            f"no school path is defined for merge kind {kind!r} — refusing "
            "rather than merging unguarded"
        ) from exc
    value: Any = row
    for attr in path:
        value = getattr(value, attr, _MISSING)
        if value is _MISSING or value is None:
            raise MergeBlockedError(
                f"cannot resolve the owning school of this {kind} record "
                f"(no {attr!r}) — refusing rather than merging unguarded"
            )
    return value


def inbound_fk_fields(person_model) -> list[tuple[Any, Any]]:
    """Every ``(model, field)`` in the registry whose FK/OneToOne targets
    ``person_model`` — including auto-created m2m through tables, which is
    what makes the walker self-maintaining."""
    out: list[tuple[Any, Any]] = []
    for model in django_apps.get_models(include_auto_created=True):
        for field in model._meta.get_fields():
            if not getattr(field, "is_relation", False):
                continue
            if not (field.many_to_one or field.one_to_one):
                continue
            if not getattr(field, "concrete", False):
                continue
            if field.related_model is person_model:
                out.append((model, field))
    return out


def _resolve_pair(op):
    person_model = person_model_for(op.kind)
    primary = person_model._default_manager.filter(pk=op.primary_pk).first()  # tenant-isolation-allow: pk-from-operation-row-school-checked-below
    secondary = person_model._default_manager.filter(pk=op.secondary_pk).first()  # tenant-isolation-allow: pk-from-operation-row-school-checked-below
    if primary is None or secondary is None:
        raise MergeBlockedError("primary or secondary record not found")
    for row, label in ((primary, "primary"), (secondary, "secondary")):
        if str(row_school_id(op.kind, row)) != str(op.school_id):
            raise MergeBlockedError(
                f"{label} record belongs to a different school — merge is "
                "same-school only (cross-school moves are transfers)"
            )
    if getattr(secondary, "merged_into_id", None):
        raise MergeBlockedError("secondary is already merged into another record")
    return person_model, primary, secondary


def preview_merge(op) -> dict[str, Any]:
    """Count the re-point footprint per inbound relation; advance to PREVIEWED."""
    from apps.people.models_merge import RecordMergeOperation

    if op.status not in (
        RecordMergeOperation.Status.DRAFT,
        RecordMergeOperation.Status.PREVIEWED,
    ):
        raise MergeBlockedError(f"cannot preview from {op.status!r}")
    person_model, _primary, secondary = _resolve_pair(op)

    plan: dict[str, int] = {}
    for model, field in inbound_fk_fields(person_model):
        try:
            count = model._default_manager.filter(**{field.name: secondary}).count()  # tenant-isolation-allow: walker-scoped-via-secondary-person-row-same-school
        except Exception:  # noqa: BLE001 — unmanaged/abstract edge: skip, never block preview
            continue
        if count:
            plan[f"{model._meta.label_lower}.{field.name}"] = int(count)

    op.preview = {
        "repoint": plan,
        "total_rows": int(sum(plan.values())),
        "generated_at": timezone.now().isoformat(),
    }
    op.save(update_fields=["preview", "updated_at"])
    op.advance(RecordMergeOperation.Status.PREVIEWED, note=f"{sum(plan.values())} rows across {len(plan)} relations")
    return op.preview


def approve_merge(op, actor) -> None:
    from apps.people.models_merge import RecordMergeOperation

    if op.status != RecordMergeOperation.Status.PREVIEWED:
        raise MergeBlockedError(f"cannot approve from {op.status!r} — preview first")
    op.approved_by = actor if getattr(actor, "pk", None) else None
    op.save(update_fields=["approved_by", "updated_at"])
    op.advance(
        RecordMergeOperation.Status.APPROVED,
        note=f"approved by {getattr(actor, 'username', '')}"[:200],
    )


def apply_merge(op, *, actor=None) -> dict[str, Any]:
    """Execute an APPROVED merge. Returns a summary dict."""
    from django.core.cache import cache

    from apps.people.models_merge import RecordMergeOperation

    lock_key = f"rmc-merge-run-{op.pk}"
    if not cache.add(lock_key, "1", timeout=600):  # magic-number-allow: single-flight-lock-ttl-seconds
        raise MergeBlockedError("a merge run is already in flight for this operation")
    try:
        op.refresh_from_db()
        if op.status != RecordMergeOperation.Status.APPROVED:
            raise MergeBlockedError(f"operation must be approved (status={op.status!r})")
        person_model, primary, secondary = _resolve_pair(op)

        op.advance(RecordMergeOperation.Status.APPLYING)
        try:
            summary = _repoint_all(op, person_model, primary, secondary)
            _retire_secondary(primary, secondary)
        except Exception as exc:  # noqa: BLE001 — walker failure lands FAILED, never half-silent
            op.advance(
                RecordMergeOperation.Status.FAILED,
                note=f"apply failed: {exc}"[:400],
            )
            raise
        op.completed_at = timezone.now()
        op.save(update_fields=["completed_at", "updated_at"])
        op.advance(
            RecordMergeOperation.Status.APPLIED,
            note=(
                f"repointed {summary['repointed']} rows; "
                f"{len(op.collisions or [])} quarantined"
            ),
        )
        _stamp_lineage(op, primary, secondary)
        _audit(op, actor)
        summary["status"] = op.status
        summary["collisions"] = len(op.collisions or [])
        return summary
    finally:
        cache.delete(lock_key)


def _is_shared_schema_model(model) -> bool:
    """True when ``model``'s table lives in the PUBLIC schema under django-tenants.

    False on a single-schema deploy (USE_DJANGO_TENANTS=0), where every tenant
    shares one table set and person pks are globally unique, so the cross-tenant
    collision this guards against cannot arise.
    """
    shared = getattr(settings, "SHARED_APPS", None)
    if not shared:
        return False
    tenant_apps = set(getattr(settings, "TENANT_APPS", ()) or ())
    app_name = model._meta.app_config.name
    return app_name in set(shared) and app_name not in tenant_apps


def _shared_schema_school_field(model) -> str | None:
    """Name of ``model``'s school FK when the model lives in the PUBLIC schema.

    Returns None for a model that is tenant-scoped (the schema itself isolates
    it, so no extra filter is needed) and raises nothing.

    Why this exists: ``inbound_fk_fields`` walks the WHOLE app registry, which is
    what makes it self-maintaining -- and correct for TENANT models, because under
    django-tenants each tenant's schema holds only its own rows. A SHARED model is
    different: ``compliance.FerpaDisclosure`` (SHARED_APPS) carries a
    ``db_constraint=False`` FK to ``people.StudentProfile`` (TENANT_APPS), so one
    public table holds every tenant's disclosure rows while StudentProfile pks are
    per-schema BigAutoField sequences that collide freely across tenants. An
    unfiltered ``filter(student=secondary).update(student=primary)`` therefore
    matches ANOTHER school's rows whose student_id happens to equal this
    secondary's pk, and re-parents that school's FERPA disclosures onto a student
    in this one.
    """
    if not _is_shared_schema_model(model):
        return None
    for field in model._meta.get_fields():
        if (
            getattr(field, "many_to_one", False)
            and getattr(field, "concrete", False)
            and getattr(field, "related_model", None) is not None
            and field.related_model._meta.label == "schools.School"
        ):
            return field.name
    return None


def _repoint_all(op, person_model, primary, secondary) -> dict[str, Any]:
    repointed = 0
    collisions: list[dict[str, Any]] = list(op.collisions or [])
    for model, field in inbound_fk_fields(person_model):
        try:
            # A SHARED-schema model is NOT isolated by the walk: see
            # _shared_schema_school_field. Constrain it to this operation's
            # school, and refuse outright when it carries no school FK -- an
            # unscopeable public table must quarantine, never be updated blind.
            extra: dict[str, Any] = {}
            school_field = _shared_schema_school_field(model)
            if school_field is not None:
                extra[school_field] = op.school_id
            elif _is_shared_schema_model(model):
                collisions.append(
                    {
                        "model": model._meta.label_lower,
                        "field": field.name,
                        "pk": "",
                        "error": (
                            "shared-schema model has no school FK; refusing to "
                            "re-point it across tenants"
                        ),
                        "at": timezone.now().isoformat(),
                    }
                )
                continue

            qs = model._default_manager.filter(**{field.name: secondary}, **extra)  # tenant-isolation-allow: tenant-models-scoped-by-schema-shared-models-scoped-by-op-school
            if not qs.exists():
                continue
            # Fast path: one bulk UPDATE under a savepoint. If ANY row in the
            # relation collides, fall back to per-row so the clean rows still
            # move and only the true collisions quarantine.
            try:
                with transaction.atomic():
                    repointed += qs.update(**{field.name: primary})
                continue
            except IntegrityError:
                pass
            for obj in model._default_manager.filter(**{field.name: secondary}, **extra).iterator():  # tenant-isolation-allow: tenant-models-scoped-by-schema-shared-models-scoped-by-op-school
                try:
                    with transaction.atomic():
                        setattr(obj, field.name, primary)
                        obj.save(update_fields=[field.name])
                    repointed += 1
                except Exception as exc:  # noqa: BLE001 — ANY per-row failure quarantines (IntegrityError, full_clean ValidationError, …), never silently skips
                    collisions.append(
                        {
                            "model": model._meta.label_lower,
                            "field": field.name,
                            "pk": str(obj.pk),
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                            "at": timezone.now().isoformat(),
                        }
                    )
        except Exception as exc:  # noqa: BLE001 — a single misbehaving relation must not strand the walk
            collisions.append(
                {
                    "model": model._meta.label_lower,
                    "field": getattr(field, "name", "?"),
                    "pk": "",
                    "error": f"relation walk failed: {type(exc).__name__}: {exc}"[:300],
                    "at": timezone.now().isoformat(),
                }
            )
    op.collisions = collisions
    op.save(update_fields=["collisions", "updated_at"])
    return {"repointed": repointed}


def _retire_secondary(primary, secondary) -> None:
    """D6 tombstone: is_active=False + merged_into where the model has it.
    Quarantined rows stay attached to this retired row — visible, undeleted."""
    update_fields = []
    if hasattr(secondary, "is_active"):
        secondary.is_active = False
        update_fields.append("is_active")
    if hasattr(secondary, "merged_into_id"):
        secondary.merged_into = primary
        update_fields.append("merged_into")
    if update_fields:
        secondary.save(update_fields=update_fields)


def _stamp_lineage(op, primary, secondary) -> None:
    try:
        from apps.metadata.models_derived_lineage import record_derived_lineage

        record_derived_lineage(
            output=primary,
            computation=MERGE_COMPUTATION,
            inputs=[
                {"model": primary._meta.label_lower, "pk": str(secondary.pk)},
                {"model": "people.RecordMergeOperation", "pk": str(op.pk)},
            ],
            school=op.school,
            version="wave-c",
        )
    except Exception:  # noqa: BLE001 — lineage never blocks a merge
        logger.warning("record_merge.lineage_failed op=%s", op.pk)


def _audit(op, actor) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            user=actor if getattr(actor, "pk", None) else None,
            model_name="RecordMergeOperation",
            object_id=str(op.pk)[:200],
            object_repr=(
                f"{op.kind} merge {op.secondary_pk} → {op.primary_pk} ({op.status})"
            )[:200],
            app_label="people",
            new_values={
                "status": op.status,
                "collisions": len(op.collisions or []),
            },
        )
    except Exception:  # noqa: BLE001 — audit never blocks a merge
        logger.warning("record_merge.audit_failed op=%s", op.pk)


__all__ = [
    "MERGE_COMPUTATION",
    "MergeBlockedError",
    "apply_merge",
    "approve_merge",
    "inbound_fk_fields",
    "person_model_for",
    "preview_merge",
]
