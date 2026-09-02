"""What each lander actually writes -- the declaration the pre-import guard reads.

WHY A TABLE AND NOT A SCAN AT RUNTIME
-------------------------------------
The guard in ``orchestrator._apply_bundle_inner`` has to answer "which of these rows
can never leave this box" *before* the first write, on a box that may be a Raspberry
Pi. It cannot AST-parse 35 modules to find out, and it must not depend on source files
being present. So the answer is a table.

A hand-written table rots. This one is MEASURED and then SEALED:

  * ``scripts/audit_lander_write_reachability.py`` resolves what the landers write by
    inter-procedural AST analysis -- through ``_helpers``, through models carried in a
    keyword, through models carried in a tuple, and through helper return values.
  * ``--check-declaration`` compares that resolution against THIS table and exits
    non-zero on any difference, in either direction.
  * ``apps/migration_cloud/tests/test_edge_write_reachability_2026_09_02.py`` runs the
    same comparison, so a lander that starts writing a new model fails a test in the
    same commit rather than silently widening what a box strands.

WHY IT IS NOT ".objects.create"
--------------------------------
A pattern scan of the landers finds 21 models. This table has 38. The gap is the
package's dominant idiom -- ``upsert_with_conflict_detection(model=Route, ...)`` --
under which the model name never appears next to a write call at all. Every
first-class lander shipped since v3.26 writes that way, so a ``.objects.create`` scan
of ``transport_lander`` concludes it writes nothing while it writes every bus route a
school has.

THE ROW EVERY DOMAIN HAS
-------------------------
``metadata.DynamicFieldValue`` / ``DynamicFieldDefinition`` appear under all 33
domains and are on nobody's rail. That is not an oversight in the table: the
orchestrator's residual-capture net (``orchestrator._ResidualCapture``) runs behind
EVERY lander that leaves ``sweeps_custom_columns`` False -- which is all of them --
and persists every unmapped source column there. So "no source column is ever
dropped" and "every domain writes at least one model that cannot sync" are the same
sentence read from two ends.
"""
from __future__ import annotations

# --- The measured table -----------------------------------------------------
# Regenerate with:
#     python scripts/audit_lander_write_reachability.py --json
# Verify with:
#     python scripts/audit_lander_write_reachability.py --check-declaration
DOMAIN_WRITE_TARGETS: dict[str, tuple[str, ...]] = {
    "academic_sessions": (
        "academics.AcademicYear",
        "academics.Term",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
    ),
    "academics": (
        "academics.Subject",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "alumni": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.StudentProfile",
    ),
    "athletics_fixtures": (
        "athletics.Fixture",
        "athletics.FixtureResult",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "athletics_memberships": (
        "athletics.TeamMembership",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "athletics_teams": (
        "athletics.Season",
        "athletics.Sport",
        "athletics.Team",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "attendance": (
        "academics.Attendance",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
    ),
    "behavior": (
        "academics.Incident",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
    ),
    "cafeteria": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "schoolops.CanteenMeal",
    ),
    "cafeteria_assignments": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
        "schoolops.MealPlanBalance",
    ),
    "communications": (
        "communication.Message",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
    ),
    "compliance": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
    ),
    "custom_fields": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
    ),
    "enrollment": (
        "academics.Classroom",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.StudentProfile",
    ),
    "events": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "school_events.SchoolEvent",
    ),
    "finance": (
        "finance.Invoice",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
    ),
    "grades": (
        "evals.Evaluation",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
    ),
    "guardians": (
        "accounts.User",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.StudentGuardian",
    ),
    "health": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "schoolops.HealthRecord",
    ),
    "hostel": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "schoolops.Hostel",
        "schoolops.HostelRoom",
    ),
    "hostel_assignments": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
        "schoolops.HostelAssignment",
    ),
    "library": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "schoolops.LibraryItem",
    ),
    "payroll": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "reports": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
    ),
    "schedule": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
    ),
    "sections": (
        "academics.AcademicYear",
        "academics.Classroom",
        "academics.Department",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "specialties": (
        "academics.Department",
        "academics.Specialty",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
    ),
    "staff": (
        "academics.Department",
        "accounts.User",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationBundle",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.TeacherProfile",
    ),
    "structure": (
        "academics.AcademicYear",
        "academics.Classroom",
        "academics.Department",
        "academics.Specialty",
        "academics.Subject",
        "academics.SubjectAssignment",
        "academics.Term",
        "accounts.User",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
        "people.TeacherProfile",
    ),
    "students": (
        "academics.Classroom",
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationBundle",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.StudentProfile",
    ),
    "transcripts": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "people.TranscriptVaultItem",
    ),
    "transport": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationConflict",
        "migration_cloud.MigrationIdMapping",
        "schoolops.Route",
    ),
    "transport_assignments": (
        "metadata.DynamicFieldDefinition",
        "metadata.DynamicFieldValue",
        "migration_cloud.MigrationIdMapping",
        "schoolops.TransportAssignment",
    ),
}

# The catch-all every canonical domain without its own lander falls through to
# (``orchestrator._apply_artifact``: ``get_lander(domain) or get_lander("custom_fields")``).
FALLBACK_DOMAIN = "custom_fields"

# The importer's OWN bookkeeping. These carry a ``school`` FK, so they are
# tenant-scoped by the same definition ``edge_rail_coverage`` uses, and they are just
# as unable to sync -- but they are not the school's records. An id-mapping row exists
# so a RE-import can recognise a row it already landed; it is regenerated by the next
# import and losing it costs an operator nothing.
#
# They are reported SEPARATELY rather than dropped. A guard that quietly excluded rows
# from a stranded census would be making exactly the judgement the operator is
# supposed to make, and hiding the evidence for it.
IMPORT_BOOKKEEPING_MODELS: frozenset[str] = frozenset({
    "migration_cloud.MigrationBundle",
    "migration_cloud.MigrationConflict",
    "migration_cloud.MigrationIdMapping",
})


def write_targets_for(domain: str) -> tuple[str, ...]:
    """Models a bundle artifact classified as ``domain`` will write.

    An unregistered domain is NOT an empty answer: the orchestrator hands it to the
    ``custom_fields`` catch-all, which writes the whole row to ``DynamicFieldValue``.
    Returning () there would report a brand-new domain as costing nothing to import,
    when it is in fact the WORST case -- everything it holds lands somewhere the rail
    does not carry.
    """
    return DOMAIN_WRITE_TARGETS.get(domain) or DOMAIN_WRITE_TARGETS[FALLBACK_DOMAIN]


def is_import_bookkeeping(model_label: str) -> bool:
    return model_label in IMPORT_BOOKKEEPING_MODELS


def school_data_targets_for(domain: str) -> tuple[str, ...]:
    """``write_targets_for`` minus the importer's own bookkeeping."""
    return tuple(m for m in write_targets_for(domain) if not is_import_bookkeeping(m))


def all_written_models() -> frozenset[str]:
    out: set[str] = set()
    for labels in DOMAIN_WRITE_TARGETS.values():
        out.update(labels)
    return frozenset(out)


__all__ = [
    "DOMAIN_WRITE_TARGETS",
    "FALLBACK_DOMAIN",
    "IMPORT_BOOKKEEPING_MODELS",
    "all_written_models",
    "is_import_bookkeeping",
    "school_data_targets_for",
    "write_targets_for",
]
