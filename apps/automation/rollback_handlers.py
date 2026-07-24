"""
Rollback handlers for MigrationRun (Phase 5 migration cloud, 11.1).
Each migration_type can register a handler(run, rollback_run) -> {success, message, reverted_count}.
Handlers use run.rollback_snapshot (e.g. created_ids, updated_ids) to revert.
"""

from typing import Any, Callable, Optional

_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {}


def register_rollback_handler(migration_type: str):
    """Decorator to register a rollback handler for a migration type."""

    def decorator(fn: Callable[..., dict[str, Any]]):
        _REGISTRY[migration_type] = fn
        return fn

    return decorator


def get_rollback_handler(
    migration_type: str,
) -> Optional[Callable[..., dict[str, Any]]]:
    return _REGISTRY.get(migration_type)


def registered_rollback_domains() -> list[str]:
    """Bare domain slugs that have a registered rollback handler (sorted).

    Read from the live registry (never a hardcoded list) so callers such as the
    connector rollback posture card can report — honestly — which domains a
    bundle apply can actually revert.
    """
    return sorted(_REGISTRY)


def run_rollback(run, rollback_run) -> dict[str, Any]:
    """Execute the rollback for run; returns dict with success, message, reverted_count."""
    migration_type = run.migration_type or ""
    # The bundle orchestrator writes migration_type as "<domain>:<artifact_path>"
    # (apps/migration_cloud/orchestrator.py::_create_audit_run), but handlers
    # register on the bare domain ("students"/"grades"). Resolve the exact key
    # first, then fall back to the domain prefix — otherwise every bundle rollback
    # silently no-ops (returns "No handler") while the caller flips the bundle to
    # FAILED, i.e. reverts NOTHING while claiming it did.
    handler = get_rollback_handler(migration_type)
    if not handler and ":" in migration_type:
        handler = get_rollback_handler(migration_type.split(":", 1)[0])
    if not handler:
        return {
            "success": False,
            "message": f"No rollback handler for {migration_type}.",
            "reverted_count": 0,
        }
    return handler(run, rollback_run)


@register_rollback_handler("students")
def _rollback_students(run, rollback_run) -> dict[str, Any]:
    """
    Delete StudentProfile records that were created in this migration run.
    rollback_snapshot: {"created_ids": [uuid, ...]} from student bulk-commit API.
    """
    from apps.people.models import StudentProfile

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = StudentProfile.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} student record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("grades")
def _rollback_grades(run, rollback_run) -> dict[str, Any]:
    """
    Delete Evaluation records that were created or updated in this migration run.
    rollback_snapshot: {"created_ids": [...], "updated_ids": [...]} from evals apply_import.
    """
    from apps.evals.models import Evaluation

    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
    updated_ids = snapshot.get("updated_ids") or []
    ids = list(created_ids) + list(updated_ids)
    if not ids:
        return {
            "success": True,
            "message": "No created_ids/updated_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = Evaluation.objects.filter(pk__in=ids)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} grade record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("finance")
def _rollback_finance(run, rollback_run) -> dict[str, Any]:
    """
    Delete Invoice records CREATED in this migration run.
    rollback_snapshot: {"created_ids": [...]} from the finance lander.

    Scoped to ``run.school`` (Invoice has a direct ``school`` FK), exactly like
    the students handler — a delete can never reach another school's ledger.
    Updates are NOT reverted (the lander upserts existing invoices in place);
    only rows this run created are removed. If a created invoice has since been
    referenced by a PROTECT relation (e.g. a payment), the delete raises an
    IntegrityError that ``trigger_rollback`` catches and reports as a failed
    rollback — the ledger is never left half-reverted.
    """
    from apps.finance.models import Invoice

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = Invoice.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} invoice record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("attendance")
def _rollback_attendance(run, rollback_run) -> dict[str, Any]:
    """
    Delete Attendance records CREATED in this migration run.
    rollback_snapshot: {"created_ids": [...]} from the attendance lander.
    Scoped to ``run.school`` (Attendance has a direct ``school`` FK).
    """
    from apps.academics.models import Attendance

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = Attendance.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} attendance record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("behavior")
def _rollback_behavior(run, rollback_run) -> dict[str, Any]:
    """
    Delete Incident records CREATED in this migration run.
    rollback_snapshot: {"created_ids": [...]} from the behavior lander.
    Scoped to ``run.school`` (Incident has a direct ``school`` FK). Any
    best-effort ``action_taken`` DynamicFieldValue extras keyed on the deleted
    incident pk are left behind harmlessly (they are not tracked per-run).
    """
    from apps.academics.models import Incident

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = Incident.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} behavior incident record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("guardians")
def _rollback_guardians(run, rollback_run) -> dict[str, Any]:
    """
    Delete StudentGuardian LINK records created in this migration run.
    rollback_snapshot: {"created_ids": [...]} from the guardian lander.

    StudentGuardian has no direct ``school`` FK, so the delete is scoped via
    ``student__school`` — the same field-aware scoping ``verification.py`` uses
    for this model — so it can never reach another school's rows.

    NOTE: the guardian lander may PROVISION a platform ``User`` (PARENT role,
    unusable password) when no account matched. Those User rows are NOT in
    created_ids and are deliberately NOT deleted here — a User is a shared,
    potentially-reused identity that may already have signed in; removing the
    student-guardian link is the safe, reversible action. Any orphaned unusable
    account is left for the operator.
    """
    from apps.people.models import StudentGuardian

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = StudentGuardian.objects.filter(  # tenant-isolation-allow: scoped via student__school=school
        pk__in=created_ids, student__school=school
    )
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} guardian link record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("staff")
def _rollback_staff(run, rollback_run) -> dict[str, Any]:
    """
    Delete TeacherProfile records CREATED in this migration run.
    rollback_snapshot: {"created_ids": [...]} from the staff lander.
    Scoped to ``run.school`` (TeacherProfile has a direct ``school`` FK).

    NOTE: like guardians, the staff lander may PROVISION a platform ``User``
    (TEACHER role, unusable password). Those User rows are NOT in created_ids and
    are deliberately NOT deleted — removing the profile is the safe, reversible
    action; the orphaned unusable account is left for the operator.
    """
    from apps.people.models import TeacherProfile

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = TeacherProfile.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} staff profile record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("enrollment")
def _rollback_enrollment(run, rollback_run) -> dict[str, Any]:
    """
    Enrollment is NOT auto-revertible, and this handler says so honestly rather
    than claim a revert that did not happen.

    The enrollment lander MUTATES existing ``StudentProfile`` rows in place
    (grade_level / status / section / classroom / academic_year) and creates
    NOTHING — so there are no created_ids to delete, and deleting the student
    would destroy a record that predates this run. The apply captured no
    pre-update values (``old`` is empty in the snapshot), so the prior
    enrollment state cannot be restored.
    """
    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
    updated = snapshot.get("updated_ids_with_old_values") or []

    # Defensive: if a future lander revision ever records genuinely-created rows,
    # delete only those, school-scoped — never touch pre-existing students.
    if created_ids:
        school = getattr(run, "school", None)
        if not school:
            return {"success": False, "message": "Run has no school.", "reverted_count": 0}
        from apps.people.models import StudentProfile

        qs = StudentProfile.objects.filter(pk__in=created_ids, school=school)
        count = qs.count()
        qs.delete()
        return {
            "success": True,
            "message": f"Deleted {count} student record(s) created by enrollment.",
            "reverted_count": count,
        }

    if not updated:
        return {
            "success": True,
            "message": "No created_ids/updated rows in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    return {
        "success": False,
        "message": (
            f"Enrollment rollback is not automatic: {len(updated)} student record(s) "
            "were updated in place and their prior grade/status/section values were "
            "not snapshotted, so they cannot be safely restored. Re-import the correct "
            "enrollment state to fix these fields."
        ),
        "reverted_count": 0,
    }
