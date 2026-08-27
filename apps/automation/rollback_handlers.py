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
    Delete Evaluation records this run CREATED. Rows it merely UPDATED are left alone.

    rollback_snapshot: {"created_ids": [...], "updated_ids": [...]} from
    ``apps.evals.importers.apply_import_from_preview``. That importer appends to
    ``updated_ids`` the pks of Evaluation rows that ALREADY EXISTED and were
    upserted in place (``was_created is False``) — a pre-existing grade whose score
    the import refreshed. Deleting those is not a revert, it is destruction of data
    the migration never created: a rollback of a grades import that touched 500
    existing evaluations used to delete all 500 rows outright, and the prior scores
    are unrecoverable because the importer snapshots no old values.

    So: created rows are deleted (school-scoped, like every other handler), and
    in-place updates are reported honestly as not automatically revertible — the
    same contract ``_rollback_finance`` and ``_rollback_alumni`` already state.
    """
    from apps.evals.models import Evaluation

    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
    updated_ids = snapshot.get("updated_ids") or []
    if not created_ids and not updated_ids:
        return {
            "success": True,
            "message": "No created_ids/updated_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }

    count = 0
    if created_ids:
        school = getattr(run, "school", None)
        if not school:
            return {"success": False, "message": "Run has no school.", "reverted_count": 0}
        # Evaluation has no direct school FK; scope through the student, the same
        # field-aware scoping the guardians handler uses, so a rollback can never
        # reach another school's marks.
        qs = Evaluation.objects.filter(  # tenant-isolation-allow: scoped via student__school=school
            pk__in=created_ids, student__school=school
        )
        count = qs.count()
        qs.delete()

    if updated_ids:
        note = (
            f"Deleted {count} grade record(s) created by this run. "
            f"{len(updated_ids)} pre-existing evaluation(s) were updated in place and are "
            "NOT reverted — the importer records no prior score, so deleting them would "
            "destroy grades this migration did not create. Re-import the correct marks "
            "to restore them."
        )
        return {"success": True, "message": note, "reverted_count": count}

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
    """Revert an enrollment apply — RESTORES the snapshotted prior field values
    for in-place updates (and deletes any genuinely-created rows).

    The enrollment lander MUTATES existing ``StudentProfile`` rows in place
    (status / section / joined_date / classroom / academic_year) and normally
    creates nothing. But BEFORE each overwrite it snapshots the OLD non-empty
    value of every field it is about to change into
    ``rollback_snapshot['updated_ids_with_old_values']`` as
    ``{"pk": ..., "old": {field: prior_value}}`` — so an in-place apply IS
    reversible after all: re-``setattr`` each recorded prior value and save it
    back, school-scoped so a rollback can never touch another school's student.

    Only fields present in ``old`` are restored (a field that was an empty
    fill-in rather than an overwrite was never recorded and is left as-is). A
    stringified FK old value that can no longer be assigned back is skipped
    rather than aborting the whole rollback. The created_ids branch below stays
    for a future lander revision that genuinely inserts students.
    """
    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
    updated = snapshot.get("updated_ids_with_old_values") or []
    school = getattr(run, "school", None)

    # Defensive: if a future lander revision ever records genuinely-created rows,
    # delete only those, school-scoped — never touch pre-existing students.
    if created_ids:
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

    # Restore the snapshotted prior values captured before each in-place
    # overwrite. School-scope every fetch so a rollback can never reach another
    # school's student.
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    from apps.people.models import StudentProfile

    restored = 0
    for entry in updated:
        old = (entry or {}).get("old") or {}
        pk = (entry or {}).get("pk")
        if not old or pk is None:
            continue
        student = StudentProfile.objects.filter(pk=pk, school=school).first()
        if student is None:
            continue
        restore_fields: list[str] = []
        for field_name, prior_value in old.items():
            try:
                setattr(student, field_name, prior_value)
            except Exception:  # noqa: BLE001 — a stringified FK old value can't be re-assigned; skip it, keep the rest
                continue
            restore_fields.append(field_name)
        if not restore_fields:
            continue
        try:
            student.save(update_fields=restore_fields)
        except Exception:  # noqa: BLE001 — a value that won't round-trip must not abort the whole rollback
            continue
        restored += 1

    return {
        "success": True,
        "message": f"Restored prior enrollment values on {restored} student record(s).",
        "reverted_count": restored,
    }


# ── C-4: rollback for the remaining first-class domains ─────────────────────
#
# The eight handlers above were hand-written; the rest of the canonical ontology
# (academics/sections/health/library/transport/… + the schoolops assignments +
# athletics + the DFV domains) landed rows but had NO rollback handler, so a
# bundle apply that touched them could not be reverted — ``run_rollback`` returned
# "No handler" while the caller flipped the bundle to FAILED, i.e. reverted
# nothing while claiming a rollback. Every domain lander appends ``created_ids``
# to its run snapshot (the ``base.Lander`` contract), so the only thing that
# varies between domains is how a landed row is scoped back to the bundle's
# school. This factory introspects the model and NEVER issues a delete without a
# school filter — if it cannot prove the scope it REFUSES (and says so) rather
# than risk reaching another school's rows. That safety property is why it is
# correct to register it across many domains from one implementation.
_GENERIC_ROLLBACK_MODELS: dict[str, tuple[str, str]] = {
    "academics": ("academics", "Subject"),
    "sections": ("academics", "Classroom"),
    "transcripts": ("people", "TranscriptVaultItem"),
    "health": ("schoolops", "HealthRecord"),
    "communications": ("communication", "Message"),
    "events": ("school_events", "SchoolEvent"),
    "library": ("schoolops", "LibraryItem"),
    "transport": ("schoolops", "Route"),
    "hostel": ("schoolops", "HostelRoom"),
    "cafeteria": ("schoolops", "CanteenMeal"),
    "transport_assignments": ("schoolops", "TransportAssignment"),
    "hostel_assignments": ("schoolops", "HostelAssignment"),
    "cafeteria_assignments": ("schoolops", "MealPlanBalance"),
    "athletics_teams": ("athletics", "Team"),
    "athletics_memberships": ("athletics", "TeamMembership"),
    "athletics_fixtures": ("athletics", "Fixture"),
    # DFV domains — the dynamic-field lander lands into a school-scoped
    # DynamicFieldValue and appends created_ids; a run that produced no first-class
    # rows simply has an empty created_ids, so the handler no-ops honestly.
    "custom_fields": ("metadata", "DynamicFieldValue"),
    "payroll": ("metadata", "DynamicFieldValue"),
    "compliance": ("metadata", "DynamicFieldValue"),
}


def _school_scoped_rollback_qs(model, created_ids, school):
    """A delete queryset scoped to ``school``, or ``None`` if scope is unprovable.

    Scope priority mirrors the hand-written handlers: a direct ``school`` FK
    (students/finance/attendance/…), else ``student__school`` (the guardians
    pattern), else ``student_profile__school`` (transcripts), else
    ``team__school`` (athletics rows), else ``hostel__school`` (hostel rooms),
    else a direct ``issuing_school`` FK. If the model carries none of these we
    return None and the caller refuses the delete — an unscoped ``pk__in`` delete
    could reach another school's rows.
    """
    field_names = {f.name for f in model._meta.get_fields()}
    if "school" in field_names:
        return model.objects.filter(pk__in=created_ids, school=school)
    if "student" in field_names:
        # tenant-isolation-allow: scoped via student__school=school (guardians pattern)
        return model.objects.filter(pk__in=created_ids, student__school=school)
    if "student_profile" in field_names:
        # tenant-isolation-allow: scoped via student_profile__school=school (transcripts)
        return model.objects.filter(pk__in=created_ids, student_profile__school=school)
    if "team" in field_names:
        # tenant-isolation-allow: scoped via team__school=school (athletics rows)
        return model.objects.filter(pk__in=created_ids, team__school=school)
    if "hostel" in field_names:
        # tenant-isolation-allow: scoped via hostel__school=school (hostel rooms)
        return model.objects.filter(pk__in=created_ids, hostel__school=school)
    if "issuing_school" in field_names:
        return model.objects.filter(pk__in=created_ids, issuing_school=school)
    return None


def _make_generic_rollback(domain: str, app_label: str, model_name: str):
    """Build a school-scoped ``created_ids`` delete handler for one domain."""

    def _handler(run, rollback_run) -> dict[str, Any]:
        from django.apps import apps as django_apps

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
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:
            return {
                "success": False,
                "message": f"Model {app_label}.{model_name} is not registered; cannot revert {domain}.",
                "reverted_count": 0,
            }
        qs = _school_scoped_rollback_qs(model, created_ids, school)
        if qs is None:
            return {
                "success": False,
                "message": (
                    f"{domain}: {model_name} carries no school / student / team scope; "
                    "refusing an unscoped delete — revert this domain manually."
                ),
                "reverted_count": 0,
            }
        count = qs.count()
        qs.delete()
        return {
            "success": True,
            "message": f"Deleted {count} {domain} record(s).",
            "reverted_count": count,
        }

    return _handler


for _domain, (_app_label, _model_name) in _GENERIC_ROLLBACK_MODELS.items():
    register_rollback_handler(_domain)(
        _make_generic_rollback(_domain, _app_label, _model_name)
    )


@register_rollback_handler("structure")
def _rollback_structure(run, rollback_run) -> dict[str, Any]:
    """Structure provisions the shared academic scaffold (AcademicYear / Term /
    Department / Classroom / Subject / SubjectAssignment) in wave 0. Those rows
    are PARENTS that later domains (enrollment / grades / sections) FK into, so
    deleting them by created_ids could orphan or PROTECT-block the dependent
    domains. It is reported honestly as non-automatic rather than claiming a
    revert that would either fail or corrupt referential integrity.
    """
    created = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created:
        return {
            "success": True,
            "message": "No scaffold rows created; nothing to revert.",
            "reverted_count": 0,
        }
    return {
        "success": False,
        "message": (
            f"Structure rollback is not automatic: {len(created)} academic-scaffold row(s) "
            "(years / terms / departments / classrooms / subjects) are shared parents that "
            "enrollment, grades and sections reference. Prune them manually only after the "
            "dependent domains have been reverted."
        ),
        "reverted_count": 0,
    }


@register_rollback_handler("academic_sessions")
def _rollback_academic_sessions(run, rollback_run) -> dict[str, Any]:
    """OneRoster academic sessions land as AcademicYear + Term calendar scaffold
    (audit D-3). Like ``structure``, those are shared PARENTS that grades /
    enrollment / sections reference, and one run's created_ids mixes two models
    (years and terms), so a blind delete could orphan or PROTECT-block dependents.
    Reported honestly as non-automatic rather than claiming an unsafe revert.
    """
    created = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created:
        return {
            "success": True,
            "message": "No academic-session rows created; nothing to revert.",
            "reverted_count": 0,
        }
    return {
        "success": False,
        "message": (
            f"Academic-session rollback is not automatic: {len(created)} year/term row(s) "
            "are shared calendar parents that grades and enrollment reference. Prune them "
            "manually only after the dependent domains have been reverted."
        ),
        "reverted_count": 0,
    }


@register_rollback_handler("alumni")
def _rollback_alumni(run, rollback_run) -> dict[str, Any]:
    """Alumni marks graduated students by flipping ``StudentProfile.status`` to
    ALUMNI (like enrollment, an in-place mutation) and creates a new profile only
    when no student matched. Genuinely-created rows ARE reverted (school-scoped);
    the in-place status flips were not snapshotted and are reported as such.
    """
    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
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
            "message": f"Deleted {count} student record(s) created by the alumni import.",
            "reverted_count": count,
        }
    return {
        "success": False,
        "message": (
            "Alumni rollback is not automatic for in-place updates: matched students had "
            "their status flipped to ALUMNI and the prior status was not snapshotted. "
            "Re-import the correct enrollment state to fix these fields."
        ),
        "reverted_count": 0,
    }
