"""Post-apply VERIFICATION — prove uploaded rows actually landed in the tenant.

``reconciliation.py`` historically computed "parity" by comparing the profiler's
source row-count against the **landers' own self-reported** created/updated counts
(pulled from the ``MigrationRun`` audit trail) — it never re-queried the tenant.
So a lander that reported ``created=100`` but whose writes were rolled back,
scoped to the wrong school, or filtered out on save would still show 100% parity.

This module re-queries each domain's REAL tenant model, **under the tenant schema
and scoped to the bundle's school**, so reconciliation can report the honest
chain ``source → landed(self-reported) → visible(actually in the school)`` and
flag drift when creates did not persist.

It mirrors :func:`apps.migration_cloud.guardrails.compute_observed_totals` (same
``schema_context`` + field-aware school scoping) but generalised to every domain
we can confidently map to a concrete model. A domain without a confident model
mapping simply returns no count (honest "not verified") rather than guessing.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# canonical domain -> (module path, model class name). The count is always scoped
# to the bundle's school: field-aware — a direct ``school`` FK, else
# ``student__school``, else unscoped under ``schema_context`` (which already
# isolates the tenant in schema-per-tenant mode). Add a domain here only once its
# landing model is confirmed; an unmapped domain reports no visible count rather
# than counting the wrong table.
_DOMAIN_MODELS: dict[str, tuple[str, str]] = {
    "students": ("apps.people.models", "StudentProfile"),
    "staff": ("apps.people.models", "TeacherProfile"),
    "guardians": ("apps.people.models", "StudentGuardian"),
    "finance": ("apps.finance.models", "Invoice"),
    # P1-Verify — extend beyond the original four so post-apply "visible in school"
    # covers the main landable domains tenants actually check.
    "attendance": ("apps.academics.models", "Attendance"),
    "grades": ("apps.evals.models", "Evaluation"),
    "behavior": ("apps.academics.models", "Incident"),
    "sections": ("apps.academics.models", "Classroom"),
    "health": ("apps.schoolops.models", "HealthRecord"),
    "events": ("apps.school_events.models", "SchoolEvent"),
    "library": ("apps.schoolops.models", "LibraryItem"),
    "transport": ("apps.schoolops.models", "Route"),
    "hostel": ("apps.schoolops.models", "HostelRoom"),
    "cafeteria": ("apps.schoolops.models", "CanteenMeal"),
    "transcripts": ("apps.people.models", "TranscriptVaultItem"),
    "athletics_teams": ("apps.athletics.models", "Team"),
    "transport_assignments": ("apps.schoolops.models", "TransportAssignment"),
    "hostel_assignments": ("apps.schoolops.models", "HostelAssignment"),
    "cafeteria_assignments": ("apps.schoolops.models", "MealPlanBalance"),
    # P1-Verify-2 (2026-07-25) — these landers write REAL, school-scoped
    # first-class rows but had no visible-count proof, so a wrong-school /
    # rolled-back / filtered-save regression on them was invisible to
    # reconciliation. Each model below carries a DIRECT ``school`` FK, so the
    # count matches the domain's self-reported creates (drift-correct):
    #   * academics  → Subject: a SIS "courses" upload; the tenant's Subjects.
    #   * structure  → SubjectAssignment: the SPLIT scaffold's created unit
    #     (one per row), which co-lands the school's Specialties/Classrooms —
    #     so a landed structure bundle is proven, incl. specialties.
    #   * communications → Message; athletics_memberships → TeamMembership;
    #     athletics_fixtures → Fixture.
    "academics": ("apps.academics.models", "Subject"),
    "structure": ("apps.academics.models", "SubjectAssignment"),
    "communications": ("apps.communication.models", "Message"),
    "athletics_memberships": ("apps.athletics.models", "TeamMembership"),
    "athletics_fixtures": ("apps.athletics.models", "Fixture"),
    # Deliberately NOT mapped: ``alumni`` lands into StudentProfile (shared with
    # ``students``) so a domain-keyed count would double-count the roster; and
    # ``payroll`` / ``compliance`` persist only DynamicFieldValue blobs (no
    # first-class model) — both stay the honest "not verified" case.
}


def domains_with_verification() -> set[str]:
    """The set of canonical domains this module can re-query. (For tests/UI.)"""
    return set(_DOMAIN_MODELS)


def _school_scoped_count(model: Any, school: Any) -> int:
    """Count rows of ``model`` visible for ``school`` (field-aware scoping).

    Models whose link to the school is not literally ``school`` / ``student``
    (``HostelRoom.hostel -> Hostel.school``, a transcripts row's ``issuing_school``,
    a ``student_profile`` FK) previously fell through to ``.all()``. In the shared-
    schema (RLS) path ``.all()`` counts EVERY school's rows, so a wrong-school write
    could never drop the visible count below the source count — drift could not fire
    and the bundle would seal + purge its encrypted source on a false "all visible".
    Recognise the indirect school paths so the visible-count check actually scopes.
    """
    field_names = {f.name for f in model._meta.get_fields()}
    if "school" in field_names:
        qs = model.objects.filter(school=school)  # tenant-isolation-allow: scoped by the model's own school FK
    elif "issuing_school" in field_names:
        qs = model.objects.filter(issuing_school=school)  # tenant-isolation-allow: scoped by the model's issuing_school FK
    elif "student" in field_names:
        qs = model.objects.filter(student__school=school)  # tenant-isolation-allow: scoped via student__school=school
    elif "student_profile" in field_names:
        qs = model.objects.filter(student_profile__school=school)  # tenant-isolation-allow: scoped via student_profile__school=school
    elif "hostel" in field_names:
        qs = model.objects.filter(hostel__school=school)  # tenant-isolation-allow: scoped via hostel__school=school (HostelRoom -> Hostel.school)
    else:
        qs = model.objects.all()  # tenant-isolation-allow: no school field; schema_context isolates the tenant
    return qs.count()


def verify_landed_counts(
    bundle: Any, *, domains: list[str] | None = None
) -> dict[str, int]:
    """Re-query the tenant and return ``{domain: rows_visible_in_school}``.

    Only domains we can confidently map to a model are returned (unmapped or
    errored domains are omitted, never guessed). Runs under the bundle's tenant
    schema so counts reflect exactly what the school actually sees. Never raises —
    a bad mapping logs a warning and is skipped so it can't break reconcile.
    """
    school = getattr(bundle, "school", None)
    if school is None:
        return {}
    schema_name = getattr(bundle, "schema_name", "") or ""

    def _run_under_schema(fn: Callable[[], Any]) -> Any:
        if not schema_name:
            return fn()
        try:
            from django_tenants.utils import schema_context
        except ImportError:
            return fn()
        with schema_context(schema_name):
            return fn()

    wanted = set(domains) if domains else None
    out: dict[str, int] = {}
    for domain, (module_path, model_attr) in _DOMAIN_MODELS.items():
        if wanted is not None and domain not in wanted:
            continue
        try:
            module = importlib.import_module(module_path)
            model = getattr(module, model_attr)
        except Exception:  # noqa: BLE001 — model unavailable in this deploy
            continue
        try:
            out[domain] = _run_under_schema(
                lambda m=model: _school_scoped_count(m, school)
            )
        except Exception:  # noqa: BLE001 — a bad mapping must never break reconcile
            logger.warning(
                "migration_cloud.verify: visible-count failed for domain=%s",
                domain,
                exc_info=True,
            )
    return out
