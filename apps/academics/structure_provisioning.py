"""Provision academic structure nodes from country pack + school types."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from apps.academics.academic_structure import AcademicStructureNode
from apps.academics.models import AcademicYear, Classroom, Department
from apps.academics.scheduling import InstructionShift
from apps.governance.academic_pack_bridge import resolve_academic_pack_context
from apps.schools.onboarding_strands import (
    namespaced_structure_code,
    resolve_provision_seed_inputs,
    strand_specialty_specs,
)


def _slug_code(prefix: str, label: str, idx: int) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in label.lower())[:20]
    return f"{prefix}-{base}-{idx}"[:30]


def ensure_general_department(school):
    """Return the single canonical "General" department for ``school``.

    Idempotent and the SOLE creator of the default department. The academic-
    structure provisioner and the Phase-B classroom seeder both need a home
    department; before this they each created their OWN "General" dept with a
    different school-namespaced code (``GEN-<id8>`` vs ``<slug>-GEN``), leaving
    every freshly provisioned tenant with two identically-named departments.
    Resolves by canonical code, then adopts any pre-existing same-named
    department (tenants seeded before this fix), else creates one.
    """
    if school is None:
        return None
    canonical_code = namespaced_structure_code(school, "GEN")
    legacy_code = f"GEN-{str(school.id)[:8]}"
    dept = Department.objects.filter(school=school, code=canonical_code).first()
    if dept is not None:
        return dept
    if legacy_code != canonical_code:
        dept = Department.objects.filter(school=school, code=legacy_code).first()
        if dept is not None:
            return dept
    # Adopt a legacy "General" department (e.g. the old <slug>-GEN one) rather
    # than minting a duplicate. Oldest wins for determinism.
    dept = (
        Department.objects.filter(school=school, name="General")
        .order_by("id")
        .first()
    )
    if dept is not None:
        return dept
    dept = Department.objects.create(
        school=school,
        code=canonical_code,
        name="General",
    )
    prefix = resolve_provision_seed_inputs(school).code_prefix
    if prefix:
        logger.info(
            "structure code prefix applied",
            extra={
                "school_id": str(getattr(school, "id", "")),
                "code_prefix": prefix,
                "department_code": dept.code,
            },
        )
    return dept


def ensure_general_specialty(school):
    """Return the single canonical "General" specialty for ``school``.

    Idempotent, and the SOLE creator of the default specialty. Nothing in
    provisioning created a Specialty at all, which quietly made a "COMPLETED"
    tenant unusable: ``FeePlan.specialty`` is a non-null FK, so no fee plan could
    be created (the automated fee task just returns ``{"status": "no_plans"}`` as
    SUCCESS), and ``SubjectAssignment.specialty`` is non-null too, so the entire
    teaching grid was unbuildable — a day-1 teacher opened the classroom dropdown
    and saw nothing, with no error to explain why.

    ``Specialty.code`` is unique per ``(school, code)``
    (``uniq_specialty_school_code``, academics migration 0085); it was GLOBALLY
    unique when this was written, which is why two schools sharing a pack
    school_type collided and the SECOND school's provisioning died on a UNIQUE
    violation. The code stays namespaced by school id anyway: the lookups here
    are school-scoped, and a per-school code is what an admin reading two
    tenants' catalogs side by side expects.
    Mirrors ``ensure_general_department``: resolve by canonical code, adopt any
    pre-existing same-named row, else create.
    """
    if school is None:
        return None
    from apps.academics.models import Specialty

    canonical_code = namespaced_structure_code(school, "SPEC", "GEN")
    legacy_code = f"SPEC-GEN-{str(school.id)[:8]}"[:30]
    specialty = Specialty.objects.filter(school=school, code=canonical_code).first()
    if specialty is not None:
        return specialty
    if legacy_code != canonical_code:
        specialty = Specialty.objects.filter(school=school, code=legacy_code).first()
        if specialty is not None:
            return specialty
    specialty = (
        Specialty.objects.filter(school=school, name="General").order_by("id").first()
    )
    if specialty is not None:
        return specialty
    return Specialty.objects.create(
        school=school,
        department=ensure_general_department(school),
        code=canonical_code,
        name="General",
    )


def ensure_strand_specialties(school, *, strand_codes: list[str] | None = None) -> dict[str, Any]:
    """Seed Specialty rows for hybrid operational strands (TVET, SEND, tracks)."""
    if school is None:
        return {"created": 0, "skipped": "no_school"}
    from apps.academics.models import Specialty
    from apps.observability.tracing import set_tags

    inputs = resolve_provision_seed_inputs(school)
    codes = list(strand_codes or inputs.strands)
    dept = ensure_general_department(school)
    ensure_general_specialty(school)
    created = 0
    codes_created: list[str] = []
    for slug, display_name in strand_specialty_specs(codes):
        canonical = namespaced_structure_code(school, "SP", slug)
        existing = Specialty.objects.filter(school=school, code=canonical).first()
        if existing is None:
            existing = (
                Specialty.objects.filter(school=school, name=display_name)
                .order_by("id")
                .first()
            )
        if existing is not None:
            continue
        Specialty.objects.create(
            school=school,
            department=dept,
            code=canonical,
            name=display_name,
        )
        created += 1
        codes_created.append(slug)
    logger.info(
        "strand specialties seeded",
        extra={
            "school_id": str(getattr(school, "id", "")),
            "strand_specialty_created": created,
            "strand_count": len(codes),
            "has_code_prefix": bool(inputs.code_prefix),
        },
    )
    try:
        set_tags(
            school_id=str(getattr(school, "id", "")),
            onboarding_strand_specialties=created,
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return {
        "created": created,
        "strand_codes": list(codes),
        "created_slugs": codes_created,
        "code_prefix": inputs.code_prefix,
    }


def ensure_school_region(school):
    """Ensure ``school.default_region`` is populated from ``country_code``.

    ``School.save`` already auto-links the region for a country, but the migration
    gap-fill path runs on an already-existing tenant that may have been created
    (or edited) with the region unset — in which case ``provision_academic_structure``
    reads an empty ISO, ``resolve_academic_pack_context("")`` returns nothing, and
    the school silently drops to a generic 3-term structure with no country cycles.
    This closes that gap defensively before provisioning. Idempotent; returns the
    region (or ``None`` when the school has no country at all — downstream then
    uses the platform GLOBAL default)."""
    if school is None:
        return None
    region = getattr(school, "default_region", None)
    if region is not None:
        return region
    iso = (getattr(school, "country_code", None) or "").strip()
    if not iso:
        return None
    try:
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        region = ensure_region_for_country(iso)
        if region is not None:
            school.default_region = region
            try:
                school.save(update_fields=["default_region"])
            except Exception:  # noqa: BLE001 — a save failure must not abort provisioning
                logger.debug("ensure_school_region: save(update_fields) failed", exc_info=True)
        return region
    except Exception:  # noqa: BLE001 — region resolution is best-effort
        logger.debug("ensure_school_region: resolve failed", exc_info=True)
        return None


def ensure_academic_year(school, *, name: str | None = None):
    """Resolve/create the school's active academic year, country-aware.

    Never overrides an existing year (the upload's own session file, or a prior
    run, wins). The start MONTH comes from :func:`_resolve_country_context` — the
    same RegionConfig/EducationSystemProfile source signup uses — so the year
    window matches the country (US August, Cameroon September, southern-hemisphere
    January) instead of a hardcoded Sept. When ``name`` is given (the migration
    path passes the tenant's ``default_academic_year_name``) the window is derived
    from it; otherwise it's derived from today. Returns ``(year, created)`` or
    ``(None, False)`` when the school is missing / a year cannot be minted."""
    if school is None:
        return None, False
    from apps.academics.models import AcademicYear

    existing = (
        AcademicYear.objects.filter(  # tenant-isolation-allow: scoped by school kwarg
            school=school, is_active=True
        )
        .order_by("-start_date")
        .first()
        or AcademicYear.objects.filter(school=school)  # tenant-isolation-allow: scoped by school kwarg
        .order_by("-start_date")
        .first()
    )
    if existing is not None:
        return existing, False

    # Link the country's region first so the start month is country-aware for
    # EVERY caller — the student lander mints the year mid-apply, before the
    # orchestrator's own region step runs, and a US school would otherwise get a
    # Sept-start year. Idempotent no-op when the region is already linked.
    ensure_school_region(school)
    start_month = _resolve_country_context(school)["start_month"]
    if name:
        years = [int(y) for y in re.findall(r"\d{4}", name)]
        start_year = years[0] if years else timezone.now().date().year
    else:
        today = timezone.now().date()
        start_year = today.year if today.month >= start_month else today.year - 1
        name = f"{start_year}/{start_year + 1}"
    year_start = date(start_year, start_month, 1)
    # Exactly one year later, minus a day — a full academic-year window that ends
    # the day before the next year would start, for any start month.
    year_end = date(start_year + 1, start_month, 1) - timedelta(days=1)
    try:
        with transaction.atomic():
            year, created = AcademicYear.objects.get_or_create(
                school=school,
                name=name,
                defaults={"start_date": year_start, "end_date": year_end, "is_active": True},
            )
        return year, created
    except Exception:  # noqa: BLE001 — best-effort; a year we cannot mint just means no scaffold
        logger.warning(
            "ensure_academic_year: could not mint year for school %s",
            getattr(school, "pk", "?"), exc_info=True,
        )
        return None, False


def forecast_academic_year(school, *, today=None) -> dict[str, Any]:
    """Predict the next editable academic-year values without writing data.

    Existing history wins over a generic calendar: the next window begins the day
    after the latest school's year ends.  A school with no history uses the same
    country-aware start-month resolver as provisioning, so raw admin and automated
    onboarding cannot suggest different calendars.
    """
    if school is None:
        return {}
    from apps.academics.models import AcademicYear

    latest = (
        AcademicYear.objects.filter(school=school)  # tenant-isolation-allow: explicit school
        .order_by("-end_date", "-start_date")
        .first()
    )
    if latest is not None and latest.end_date:
        year_start = latest.end_date + timedelta(days=1)
        try:
            next_anniversary = year_start.replace(year=year_start.year + 1)
        except ValueError:  # February 29 -> February 28 in a non-leap year
            next_anniversary = year_start.replace(
                year=year_start.year + 1, month=2, day=28
            )
        year_end = next_anniversary - timedelta(days=1)
    else:
        current = today or timezone.now().date()
        start_month = _resolve_country_context(school)["start_month"]
        start_year = (
            current.year if current.month >= start_month else current.year - 1
        )
        year_start = date(start_year, start_month, 1)
        year_end = date(start_year + 1, start_month, 1) - timedelta(days=1)
    return {
        "name": f"{year_start.year}/{year_end.year}",
        "start_date": year_start,
        "end_date": year_end,
        # A first year is useful immediately.  Later years remain inactive until
        # the governed activation action is explicitly chosen.
        "is_active": latest is None,
    }


def _resolve_country_context(school) -> dict[str, Any]:
    """Resolve a school's country-derived provisioning context ONCE.

    Returns ``{start_month, term_count, term_labels}``. Both the academic-year
    WINDOW (``ensure_academic_year``) and the Term STRUCTURE (``ensure_terms``)
    read from here, so a country's calendar can never drift between the two —
    before this, the year start month and the term split were resolved by two
    different code paths (signup's inline block vs. migration's hardcoded Sept),
    and a migrated US school got a Sept-start year while signup gave it August.

    Resolution order mirrors the canonical provisioning path
    (``apps/schools/tasks.py``): the school's ``RegionConfig`` then its resolved
    ``EducationSystemProfile`` (both derived from ``country_code``) — Cameroon
    yields 3 trimesters starting September, a US region 2 semesters starting
    August, southern-hemisphere regions January — with the GB ``term_preset``
    override. Best-effort: any resolver failure falls back to platform defaults
    (Sept start, 3 unnamed terms) rather than raising.
    """
    start_month = 9
    term_count = 3
    term_labels: list[str] = []
    region = getattr(school, "default_region", None)
    if region is not None:
        term_count = getattr(region, "term_count_per_year", 3) or 3
        start_month = int(getattr(region, "academic_year_start_month", 9) or 9)
    policy: dict = {}
    profile = None
    try:
        from apps.policies.policy_registry import get_effective_policy
        from apps.siteconfig.education_profile_engine import resolve_profile_for_school

        policy = get_effective_policy(school) or {}
        profile = resolve_profile_for_school(
            school,
            requested_profile_code=str(policy.get("education_profile_code") or "").strip(),
            auto_create=True,
        )
    except Exception:  # noqa: BLE001 — resolver is best-effort; fall back to defaults
        logger.debug("_resolve_country_context: profile/policy resolve failed", exc_info=True)
    if profile is not None:
        try:
            term_count = int(getattr(profile, "term_count_per_year", term_count) or term_count)
            term_labels = profile.normalized_term_labels() or []
            start_month = int(getattr(profile, "academic_year_start_month", start_month) or start_month)
        except Exception:  # noqa: BLE001
            pass
    if (policy.get("term_preset") or "").strip() == "UK":
        term_count = 3
        term_labels = term_labels or ["Michaelmas", "Lent", "Trinity"]
        start_month = 9
    # Guard: position CheckConstraint allows 1..12; a bad profile value can't
    # break the seeder. Month is likewise clamped to a real calendar month.
    term_count = max(1, min(12, int(term_count or 3)))
    start_month = max(1, min(12, int(start_month or 9)))
    return {"start_month": start_month, "term_count": term_count, "term_labels": term_labels}


def _resolve_term_structure(school) -> tuple[int, list[str]]:
    """Return ``(term_count, term_labels)`` for a school, keyed off its country.

    Thin wrapper over :func:`_resolve_country_context` kept for the callers (and
    tests) that only need the term half of the context."""
    ctx = _resolve_country_context(school)
    return ctx["term_count"], ctx["term_labels"]


def ensure_terms(school, academic_year) -> dict[str, Any]:
    """Idempotently seed the country/region-appropriate ``Term`` rows for a year.

    The migration path (Migration Cloud gap-fill) never runs normal onboarding, so
    a migrated school lands with an AcademicYear but NO terms — and the teaching
    grid (``provision_teaching_grid_for_school``) then returns
    ``missing_prerequisites`` and no report card can be produced. This extracts the
    canonical term-seeding (previously inline in ``apps/schools/tasks.py``) so both
    onboarding and migration converge on the same country-aware structure:
    ``RegionConfig``/``EducationSystemProfile`` drive the count + labels; term DATES
    come from the country's curated calendar (``country_term_calendars``) when one
    is known — Cameroon's real trimester windows, not an even Aug-31 third — and
    fall back to an even month split otherwise; and exactly one term ends up active
    (the marks-entry surface 403s without one). Everything stays
    admin-editable. Keyed on ``get_or_create(school, academic_year, name)`` — the
    model's ``unique_together`` — so a re-apply never duplicates. Returns a summary.
    """
    if school is None or academic_year is None:
        return {"created_terms": 0, "skipped": "no_school_or_year"}
    from apps.academics.models import Term

    year_start = getattr(academic_year, "start_date", None)
    year_end = getattr(academic_year, "end_date", None)
    if not (year_start and year_end):
        return {"created_terms": 0, "skipped": "year_missing_dates"}

    ctx = _resolve_country_context(school)
    term_count = ctx["term_count"]
    term_labels = ctx["term_labels"]

    # Real per-country term windows (Cameroon's third trimester ends in July, not
    # the Aug 31 an even split would give it). Falls back to ``None`` — the even
    # month split below — when no calendar is known for the school's country.
    # Admin-editable via ``settings['term_windows']`` / the education profile.
    from apps.academics.country_term_calendars import resolve_term_windows

    windows = resolve_term_windows(
        school, term_count,
        year_start=year_start, year_end=year_end, start_month=ctx["start_month"],
    )

    def _month_start_add(base_date: date, months: int) -> date:
        year = base_date.year + ((base_date.month - 1 + months) // 12)
        month = ((base_date.month - 1 + months) % 12) + 1
        return date(year, month, 1)

    created = 0
    months_per_term = max(1, 12 // term_count)
    for i in range(term_count):
        if windows is not None:
            t_start, t_end = windows[i]
        else:
            t_start = _month_start_add(year_start, i * months_per_term)
            if i == term_count - 1:
                t_end = year_end
            else:
                t_end = _month_start_add(year_start, (i + 1) * months_per_term) - timedelta(days=1)
            # Clamp a term start that overshoots the year (short/odd year windows)
            # so start_date never exceeds end_date.
            if t_start > year_end:
                t_start = year_start
        term_name = (
            term_labels[i]
            if i < len(term_labels) and str(term_labels[i]).strip()
            else f"Term {i + 1}"
        )
        try:
            with transaction.atomic():
                _obj, was_created = Term.objects.get_or_create(
                    school=school,
                    academic_year=academic_year,
                    name=term_name,
                    defaults={
                        "position": i + 1,
                        "start_date": t_start,
                        "end_date": t_end,
                        "is_active": i == 0,
                    },
                )
            created += 1 if was_created else 0
        except Exception:  # noqa: BLE001 — one term never aborts the rest
            logger.debug("ensure_terms: term %s seed failed", term_name, exc_info=True)

    # The year MUST end with an active term (get_or_create IGNORES the is_active
    # default when the row already existed from a partial prior run).
    if not Term.objects.filter(school=school, academic_year=academic_year, is_active=True).exists():
        first = (
            Term.objects.filter(school=school, academic_year=academic_year)
            .order_by("position", "start_date", "id")
            .first()
        )
        if first is not None:
            Term.objects.filter(school=school, pk=first.pk).update(is_active=True)

    # Record whether this calendar is a representative default (curated / even
    # split) or a real admin/operator-supplied one (school / profile override), so
    # a representative calendar can be surfaced for confirm-before-go-live. Purely
    # informational — a failure here never affects the seeded terms.
    calendar_source: str | None = "even_split"
    try:
        from apps.academics.country_term_calendars import term_windows_source
        from apps.academics.academic_calendar import record_calendar_provenance

        # ``windows is None`` means the alignment guard rejected every calendar and
        # the even split was used, regardless of what layer exists — so it is a
        # representative default. Otherwise the layer that supplied the windows
        # (school/profile override vs curated) decides representativeness.
        if windows is None:
            calendar_source = "even_split"
        else:
            calendar_source = term_windows_source(school, term_count) or "curated"
        record_calendar_provenance(school, calendar_source)
    except Exception:  # noqa: BLE001 — provenance is best-effort, never load-bearing
        logger.debug("ensure_terms: calendar provenance record failed", exc_info=True)

    return {
        "created_terms": created,
        "term_count": term_count,
        "calendar_source": calendar_source,
    }


def provision_teaching_grid_for_school(
    school,
    *,
    academic_year: AcademicYear | None = None,
) -> dict[str, Any]:
    """Seed the classroom x subject x term grid a school actually teaches from.

    THE GAP THIS CLOSES
    -------------------
    Provisioning marked a tenant COMPLETED while creating ZERO SubjectAssignments,
    and that model is the hinge the whole school day turns on: teachers reach
    classrooms through ``TeacherAssignment -> subject_assignment__classroom``, and
    marks point at a SubjectAssignment. With none, a school that provisioned
    "successfully" could not take attendance or enter a single grade — and nothing
    raised. Every surface just rendered an empty dropdown, which reads as "no data
    yet" rather than "your tenant is broken".

    Idempotent (get_or_create on the model's own unique_together) so a resume
    completes a partial grid instead of duplicating it. Honours the third-term
    rule that ``SubjectAssignment.clean()`` enforces — ``.create()`` never calls
    ``clean()``, so a blind seed would write rows the model itself considers
    invalid.
    """
    if school is None:
        return {"created_assignments": 0, "skipped": "no_school"}

    from apps.academics.models import Classroom, Subject, SubjectAssignment, Term

    year = academic_year
    if year is None:
        year = AcademicYear.objects.filter(school=school, is_active=True).first()
    if year is None:
        year = AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    if year is None:
        return {"created_assignments": 0, "skipped": "no_academic_year"}

    classrooms = list(Classroom.objects.filter(school=school, academic_year=year))
    subjects = list(Subject.objects.filter(school=school))
    terms = list(Term.objects.filter(school=school, academic_year=year).order_by("position"))
    if not (classrooms and subjects and terms):
        return {
            "created_assignments": 0,
            "skipped": "missing_prerequisites",
            "classrooms": len(classrooms),
            "subjects": len(subjects),
            "terms": len(terms),
        }

    specialty = ensure_general_specialty(school)
    if specialty is None:
        return {"created_assignments": 0, "skipped": "no_specialty"}

    created = 0
    skipped_third_term = 0
    with transaction.atomic():
        for classroom in classrooms:
            for term in terms:
                # SubjectAssignment.clean() rejects a third-term row on a
                # classroom that disallows it. create() does not call clean(), so
                # respect the rule here rather than seeding invalid rows.
                if term.position == 3 and not classroom.allows_third_term:
                    skipped_third_term += len(subjects)
                    continue
                for subject in subjects:
                    _, was_created = SubjectAssignment.objects.get_or_create(
                        academic_year=year,
                        term=term,
                        classroom=classroom,
                        specialty=specialty,
                        subject=subject,
                        defaults={"school": school},
                    )
                    if was_created:
                        created += 1

    return {
        "created_assignments": created,
        "classrooms": len(classrooms),
        "subjects": len(subjects),
        "terms": len(terms),
        "specialty_code": getattr(specialty, "code", ""),
        "skipped_third_term": skipped_third_term,
        "total_assignments": SubjectAssignment.objects.filter(
            school=school, academic_year=year
        ).count(),
    }


def provision_academic_structure_for_school(
    school,
    *,
    school_type_codes: list[str] | None = None,
    academic_year: AcademicYear | None = None,
) -> dict[str, Any]:
    """
    Build cycle nodes from localization pack school_types and optional level leaves.

    Idempotent per (school, school_type code): reuses existing cycle nodes by metadata.
    """
    if school is None:
        return {"created_nodes": 0, "created_classrooms": 0}

    iso = (getattr(school, "country_code", None) or "")[:2].upper()
    ctx = resolve_academic_pack_context(iso)
    pack = ctx.get("country_pack") or {}
    types = pack.get("school_types") or []
    selected = {c.strip().lower() for c in (school_type_codes or []) if c}
    if selected:
        types = [t for t in types if str(t.get("code", "")).lower() in selected]

    year = academic_year
    if year is None:
        year = (
            AcademicYear.objects.filter(school=school).order_by("-start_date").first()
        )
    if year is None:
        return {"created_nodes": 0, "created_classrooms": 0, "skipped": "no_academic_year"}

    dept = ensure_general_department(school)
    strand_payload = ensure_strand_specialties(school)

    created_nodes = 0
    created_classrooms = 0

    with transaction.atomic():
        for idx, st in enumerate(types):
            code = str(st.get("code") or f"type-{idx}")
            label = str(st.get("label") or code)
            cycle = AcademicStructureNode.objects.filter(
                school=school,
                node_type=AcademicStructureNode.NodeType.CYCLE,
                structural_metadata__pack_school_type=code,
            ).first()
            if cycle is None:
                cycle = AcademicStructureNode.objects.create(
                    school=school,
                    parent=None,
                    node_type=AcademicStructureNode.NodeType.CYCLE,
                    local_label=label,
                    sort_order=idx * 10,
                    structural_metadata={
                        "pack_school_type": code,
                        "primary_sector": st.get("primary_sector"),
                    },
                )
                created_nodes += 1

            if st.get("primary_sector") in ("secondary", "middle", "k12"):
                class_label = f"{label} — Group A"
                # Classroom.code is unique per (school, code)
                # (``uniq_classroom_school_code``, academics migration 0085); it
                # was GLOBALLY unique when this was written, which is why two
                # schools sharing a pack school_type (e.g. two US "high" schools)
                # generated the same code and the SECOND school's provisioning
                # died with a UNIQUE collision (the "provisioning fails for the
                # next school" bug). The code stays namespaced by school id: the
                # lookup below is school-scoped, and a per-school code keeps two
                # tenants' catalogs readable side by side. Mirrors dept_code.
                sid = str(getattr(school, "id", "")).replace("-", "")[:8]
                prefix = resolve_provision_seed_inputs(school).code_prefix
                room_stem = (
                    f"{sid}-{prefix}-{code}" if prefix else f"{sid}-{code}"
                )
                room_code = _slug_code(room_stem, label, 0)
                classroom = Classroom.objects.filter(
                    school=school, academic_year=year, code=room_code
                ).first()
                if classroom is None:
                    classroom = Classroom.objects.create(
                        school=school,
                        academic_year=year,
                        department=dept,
                        name=class_label,
                        code=room_code,
                    )
                    created_classrooms += 1
                leaf = AcademicStructureNode.objects.filter(
                    school=school,
                    classroom=classroom,
                ).first()
                if leaf is None:
                    AcademicStructureNode.objects.create(
                        school=school,
                        parent=cycle,
                        node_type=AcademicStructureNode.NodeType.CLASSROOM_LEAF,
                        local_label=class_label,
                        sort_order=0,
                        structural_metadata={"pack_school_type": code},
                        classroom=classroom,
                    )
                    created_nodes += 1

    shifts_created = _ensure_default_instruction_shifts(school, iso)

    return {
        "created_nodes": created_nodes,
        "created_classrooms": created_classrooms,
        "school_types_processed": len(types),
        "shifts_created": shifts_created,
        "strand_specialties": strand_payload,
    }


def _ensure_default_instruction_shifts(school, country_code: str) -> int:
    """Seed morning/afternoon shifts when the country pack supports multi-shift."""
    ctx = resolve_academic_pack_context(country_code)
    if not ctx.get("supports_multi_shift"):
        return 0
    created = 0
    for code, label, order in (
        ("morning", "Morning (matinée)", 0),
        ("afternoon", "Afternoon (vespertina)", 10),
    ):
        _, was_created = InstructionShift.objects.get_or_create(
            school=school,
            code=code,
            defaults={"label": label, "sort_order": order},
        )
        if was_created:
            created += 1
    return created


def seed_country_subjects(school) -> dict[str, Any]:
    """Seed the country/education-system default Subject catalog when the school
    has NONE — bringing the migration path to parity with signup.

    A roster-only export lands students but no subjects, so the teaching grid
    stays empty (``missing_prerequisites``) and no report card can be produced.
    Onboarding already seeds these subjects at signup; this makes the SAME seed
    available to a migrated school, so a bare export still yields a runnable
    school on day one.

    NEVER touches an existing catalog — an uploaded ``Subject`` list always wins
    (idempotent guard on ``count() == 0``). The seed is the school's own
    Education-DNA ``subject_seed`` (the country-pack override, e.g. Cameroon's
    Mathematics/English/Biology/…, or the language-aware Math/English/Science
    fallback), NOT a per-upload invention — and every row it creates is a plain
    admin-editable ``Subject``. Mirrors the signup seeding in
    ``apps/schools/tasks.py`` so both doors seed the same catalog."""
    if school is None:
        return {"created_subjects": 0, "skipped": "no_school"}
    from apps.academics.models import Subject

    existing = Subject.objects.filter(school=school).count()
    if existing:
        return {"created_subjects": 0, "skipped": "catalog_exists", "existing": existing}

    subject_seed: list[dict] = []
    try:
        from apps.policies.policy_registry import get_effective_policy
        from apps.siteconfig.education_profile_engine import resolve_profile_for_school

        policy = get_effective_policy(school) or {}
        profile = resolve_profile_for_school(
            school,
            requested_profile_code=str(policy.get("education_profile_code") or "").strip(),
            auto_create=True,
        )
        if profile is not None:
            subject_seed = profile.normalized_subject_seed() or []
    except Exception:  # noqa: BLE001 — profile resolve is best-effort
        logger.debug("seed_country_subjects: profile resolve failed", exc_info=True)

    if not subject_seed:
        # Last-resort language-aware fallback (no resolved profile / empty seed),
        # exactly as signup does — an English-medium school never gets French as a
        # core subject.
        try:
            from apps.siteconfig.education_profile_engine import _default_subject_seed

            fallback_lang = (getattr(school, "default_language", "") or "").strip()
            if not fallback_lang:
                sub_system = (getattr(school, "sub_system", "") or "").upper()
                fallback_lang = "fr" if sub_system == "FR" else "en"
            subject_seed = _default_subject_seed(fallback_lang) or []
        except Exception:  # noqa: BLE001
            logger.debug("seed_country_subjects: fallback seed failed", exc_info=True)

    if not subject_seed:
        return {"created_subjects": 0, "skipped": "no_seed"}

    from apps.academics.country_subject_codes import build_override_map, resolve_subject_code

    # Resolve the DB-backed override layer (profile + school) ONCE for the whole
    # catalog rather than re-resolving the education-system profile per subject.
    override_map = build_override_map(school)
    valid_categories = {choice[0] for choice in Subject.Category.choices}
    created = 0
    names: list[str] = []
    for item in subject_seed:
        name = str(item.get("name") if isinstance(item, dict) else item or "").strip()
        if not name:
            continue
        raw_category = str(
            item.get("category", Subject.Category.GENERAL)
            if isinstance(item, dict)
            else Subject.Category.GENERAL
        ).upper()
        category = raw_category if raw_category in valid_categories else Subject.Category.GENERAL
        try:
            _, was_created = Subject.objects.get_or_create(
                school=school,
                name=name,
                defaults={"category": category, "code": resolve_subject_code(school, name, override_map=override_map)},
            )
            if was_created:
                created += 1
                names.append(name)
        except Exception:  # noqa: BLE001 — one bad subject never aborts the rest
            logger.debug("seed_country_subjects: subject %s failed", name, exc_info=True)
    return {"created_subjects": created, "catalog": names}


def backfill_subject_codes(school) -> dict[str, Any]:
    """Fill a national/country-standard ``code`` on every subject that has none.

    Newly seeded subjects already carry a code; this brings UPLOADED catalogs
    (which land as bare name-only ``Subject`` rows) up to the same standard, and
    backfills tenants provisioned before ``Subject.code`` existed. Only touches
    BLANK codes — an admin's explicit code always wins — so it is idempotent and
    safe to re-run. Country-aware via
    :func:`apps.academics.country_subject_codes.resolve_subject_code`."""
    if school is None:
        return {"coded_subjects": 0, "skipped": "no_school"}
    from apps.academics.country_subject_codes import build_override_map, resolve_subject_code
    from apps.academics.models import Subject

    override_map = build_override_map(school)
    coded = 0
    for subject in Subject.objects.filter(school=school).filter(code=""):
        code = resolve_subject_code(school, subject.name, override_map=override_map)
        if not code:
            continue
        try:
            Subject.objects.filter(school=school, pk=subject.pk).update(code=code)
            coded += 1
        except Exception:  # noqa: BLE001 — one subject never aborts the rest
            logger.debug("backfill_subject_codes: subject %s failed", subject.name, exc_info=True)
    return {"coded_subjects": coded}


def resync_subject_codes(school, *, dry_run: bool = False) -> dict[str, Any]:
    """Propagate a newly-imported official code to subjects seeded BEFORE the import.

    ``backfill_subject_codes`` only fills BLANK codes, so a subject seeded with the
    old mnemonic default keeps it even after an operator imports a country's real
    official codes into the shared profile — the report card would still show the
    mnemonic. This closes that gap: it re-resolves every non-blank subject and, when
    the stored code is a recognizable SYSTEM DEFAULT (the curated table value or the
    mnemonic) that no longer matches the resolved code, updates it to the new value.

    An admin's explicit custom code (which matches no default) and an
    already-correct code are both left untouched, so this is safe and idempotent —
    the ``code``-write twin of the term-window override cascade. ``dry_run`` reports
    the exact ``old → new`` diffs without writing."""
    if school is None:
        return {"resynced_subjects": 0, "skipped": "no_school", "changes": []}
    from apps.academics.country_subject_codes import (
        build_override_map,
        is_default_subject_code,
        resolve_subject_code,
    )
    from apps.academics.models import Subject

    override_map = build_override_map(school)
    if not override_map:
        # No override layer to propagate — nothing an import could have changed.
        return {"resynced_subjects": 0, "changes": []}
    resynced = 0
    changes: list[dict[str, str]] = []
    for subject in Subject.objects.filter(school=school).exclude(code=""):
        resolved = resolve_subject_code(school, subject.name, override_map=override_map)
        if not resolved or resolved == subject.code:
            continue
        if not is_default_subject_code(school, subject.name, subject.code):
            continue  # an admin's explicit edit — never clobber
        changes.append({"subject": subject.name, "old": subject.code, "new": resolved})
        if not dry_run:
            try:
                Subject.objects.filter(school=school, pk=subject.pk).update(code=resolved)
            except Exception:  # noqa: BLE001 — one subject never aborts the rest
                logger.debug("resync_subject_codes: subject %s failed", subject.name, exc_info=True)
                continue
        resynced += 1
    return {"resynced_subjects": resynced, "changes": changes}


def ensure_admission_template(school) -> dict[str, Any]:
    """Seed a school's country-default admission-number template so new admission
    numbers follow the local standard instead of the generic fallback.

    Fills the previously-EMPTY ``country_defaults`` admission layer of the policy
    cascade, but applied SAFELY per-tenant (never in the global resolver, which
    would change the format under every un-configured tenant). Two guards keep it
    from ever changing a school's format mid-stream:

      * only when the school has NO ``TenantAdmissionNumberPolicy`` yet, and
      * only when NO student has been stamped with an admission number yet — so a
        migration that already issued its roster's numbers is left untouched.

    Stored on ``TenantAdmissionNumberPolicy`` (strategy TEMPLATE), the dedicated
    per-tenant, admin-editable model the generator reads first. Idempotent."""
    if school is None:
        return {"skipped": "no_school"}
    try:
        from apps.people.models import StudentProfile
        from apps.siteconfig.identifier_policy_service import default_school_code_for
        from apps.siteconfig.models import TenantAdmissionNumberPolicy
    except Exception:  # noqa: BLE001 — optional dependency wiring
        return {"skipped": "import_error"}

    if TenantAdmissionNumberPolicy.objects.filter(school=school).exists():
        return {"skipped": "policy_exists"}
    # admission_number is blank="" OR null — a school that has stamped ANY real
    # number must keep its format; only skip the truly-empty rows.
    if (
        StudentProfile.objects.filter(school=school)  # tenant-isolation-allow: scoped by school kwarg
        .filter(admission_number__isnull=False)
        .exclude(admission_number="")
        .exists()
    ):
        return {"skipped": "numbers_already_issued"}

    template = ""
    try:
        from apps.policies.country_admission_templates import resolve_admission_template

        template = resolve_admission_template(school) or ""
    except Exception:  # noqa: BLE001 — template resolve is best-effort
        logger.debug("ensure_admission_template: resolve failed", exc_info=True)
    if not template:
        return {"skipped": "no_template"}

    try:
        TenantAdmissionNumberPolicy.objects.create(
            school=school,
            strategy="TEMPLATE",
            template=template,
            school_code=default_school_code_for(school),
            is_active=True,
        )
        return {"template": template}
    except Exception:  # noqa: BLE001 — a policy we cannot mint just means the generic default
        logger.debug("ensure_admission_template: create failed", exc_info=True)
        return {"skipped": "create_failed"}


_VOCATIONAL_MARKERS = ("tvet", "vocational", "technical", "trade", "polytechnic")


def _is_vocational_school(school) -> bool:
    """True when a school reads as vocational/TVET — the gate for seeding trades.

    A general-ed school must NEVER sprout a welding specialty, so this is
    deliberately conservative: it fires only on an explicit vocational marker in
    the school's declared type (``settings['school_type']`` / ``school_type_raw``
    / ``education_type``) or an ``education_system_types`` registry code."""
    if school is None:
        return False
    settings_map = getattr(school, "settings", None) or {}
    blob = " ".join(
        str(settings_map.get(k) or "")
        for k in ("school_type", "school_type_raw", "education_type")
    ).lower()
    if any(m in blob for m in _VOCATIONAL_MARKERS):
        return True
    try:
        codes = " ".join(
            str(c).lower()
            for c in school.education_system_types.values_list("code", flat=True)
        )
        if any(m in codes for m in _VOCATIONAL_MARKERS):
            return True
    except Exception:  # noqa: BLE001 — M2M may be unavailable; best-effort signal
        pass
    return False


def seed_country_trades(school) -> dict[str, Any]:
    """Seed a vocational school's country-default trades (Specialty rows under
    grouping Departments) when it has none of its own.

    The platform shipped no trade catalog at all, so a TVET school onboarding
    fresh — or a roster-only export that never listed its trades — landed with a
    single "General" specialty and nowhere to place a student's course of study.
    This gives it a country-appropriate default set (Cameroon's Welding / Plumbing
    / Catering / … or the universal generic set) so it runs on day one.

    Gated to vocational schools only. Skipped when the school already has a real
    (non-"General") specialty — an uploaded trade list always wins.
    ``Department.code`` and ``Specialty.code`` are unique per ``(school, code)``
    (``uniq_department_school_code`` / ``uniq_specialty_school_code``), so a code
    only has to be unique WITHIN this school — but it is namespaced by school id
    AND index anyway (never the truncated name: a long name truncated to 30 chars
    collapses distinct codes to one, which collides inside a single school).
    Idempotent + admin-editable."""
    if school is None:
        return {"created_specialties": 0, "skipped": "no_school"}
    if not _is_vocational_school(school):
        return {"created_specialties": 0, "skipped": "not_vocational"}
    from apps.academics.models import Department, Specialty

    existing = Specialty.objects.filter(school=school).exclude(name="General").count()
    if existing:
        return {"created_specialties": 0, "skipped": "specialties_exist", "existing": existing}

    catalog = None
    try:
        from apps.academics.country_trade_catalogs import resolve_trade_catalog

        catalog = resolve_trade_catalog(school)
    except Exception:  # noqa: BLE001 — catalog resolve is best-effort
        logger.debug("seed_country_trades: catalog resolve failed", exc_info=True)
    if not catalog:
        return {"created_specialties": 0, "skipped": "no_catalog"}

    # 12 hex chars (48 bits) of the UUID, not 8. Department.code/Specialty.code
    # are unique per (school, code), so this prefix is no longer load-bearing for
    # correctness — it is kept because a readable per-school namespace is worth
    # more than four characters, and an 8-hex (32-bit) prefix had a non-trivial
    # birthday-collision chance across tens of thousands of tenants back when the
    # column WAS global. Codes stay well under 30 chars (index part FIRST so a
    # [:30] truncation can't collapse two distinct codes onto one).
    sid = str(getattr(school, "id", "")).replace("-", "")[:12]
    created_depts = 0
    created_specs = 0
    trades: list[str] = []
    # NO outer atomic: each create gets its OWN savepoint so a rare cross-school
    # code collision (IntegrityError) rolls back only that row instead of poisoning
    # the surrounding transaction — which would make the very NEXT query raise
    # TransactionManagementError and abort the entire baseline.
    for d_idx, (dept_name, trade_names) in enumerate(catalog):
        dept_code = f"{sid}-TD{d_idx}"[:30]
        dept = (
            Department.objects.filter(school=school, name=dept_name).first()
            or Department.objects.filter(school=school, code=dept_code).first()
        )
        if dept is None:
            try:
                with transaction.atomic():
                    dept = Department.objects.create(
                        school=school, name=dept_name, code=dept_code
                    )
                created_depts += 1
            except Exception:  # noqa: BLE001 — a dept-code collision skips it, never poisons the txn
                logger.debug(
                    "seed_country_trades: department %s failed", dept_name, exc_info=True
                )
                dept = Department.objects.filter(school=school, name=dept_name).first()
        if dept is None:
            continue
        for s_idx, trade_name in enumerate(trade_names):
            if Specialty.objects.filter(school=school, name=trade_name).exists():
                continue
            spec_code = f"{sid}-TR{d_idx}-{s_idx}"[:30]
            try:
                with transaction.atomic():
                    Specialty.objects.create(
                        school=school, department=dept, name=trade_name, code=spec_code
                    )
                created_specs += 1
                trades.append(trade_name)
            except Exception:  # noqa: BLE001 — one trade's collision never aborts the rest
                logger.debug(
                    "seed_country_trades: specialty %s failed", trade_name, exc_info=True
                )
    return {
        "created_specialties": created_specs,
        "created_departments": created_depts,
        "trades": trades,
    }


def ensure_specialty_curriculum(school) -> dict[str, Any]:
    """Seed the specialty↔subject curriculum (``SpecialtySubject``) with a
    permissive default: every subject linked to every specialty, which an admin
    then trims per trade.

    The platform had no curriculum graph, so a teacher roster's subject id-lists
    could not become assignments and the grid could only be built under "General".
    Seeding a default curriculum makes both possible while staying editable.
    Idempotent (get_or_create on the unique (specialty, subject))."""
    if school is None:
        return {"created_links": 0, "skipped": "no_school"}
    from apps.academics.models import Specialty, SpecialtySubject, Subject

    subjects = list(Subject.objects.filter(school=school))
    specialties = list(Specialty.objects.filter(school=school))
    if not (subjects and specialties):
        return {"created_links": 0, "skipped": "missing_subjects_or_specialties"}

    created = 0
    with transaction.atomic():
        for sp in specialties:
            for subj in subjects:
                _, was_created = SpecialtySubject.objects.get_or_create(
                    specialty=sp, subject=subj, defaults={"school": school}
                )
                created += 1 if was_created else 0
    return {
        "created_links": created,
        "specialties": len(specialties),
        "subjects": len(subjects),
    }


def resolve_specialty_subjects(school, specialty) -> list:
    """Subjects in a specialty's curriculum, or ALL of the school's subjects when
    the specialty has no explicit curriculum yet (so the grid always has
    something to build)."""
    from apps.academics.models import Subject

    subs = list(
        Subject.objects.filter(
            school=school, specialty_links__specialty=specialty
        ).distinct()
    )
    if subs:
        return subs
    return list(Subject.objects.filter(school=school))


def provision_per_specialty_grid(
    school, *, academic_year: AcademicYear | None = None
) -> dict[str, Any]:
    """Build the teaching grid for the (classroom, specialty) pairs that ENROLLED
    students actually occupy — so a student on a TVET trade (not "General") has
    matching ``SubjectAssignment`` rows and can be graded / get a report card.

    ``Evaluation.clean`` requires ``student.specialty == assignment.specialty``
    (and classroom), so the General-only grid left every trade student
    ungradeable. This is STUDENT-DRIVEN — it enumerates the distinct
    (classroom, specialty) pairs present in the roster, never a cartesian
    explosion — and curriculum-aware (uses each specialty's ``SpecialtySubject``
    list, all subjects as fallback). Idempotent + honours the third-term rule."""
    if school is None:
        return {"created_assignments": 0, "skipped": "no_school"}
    from apps.academics.models import (
        Classroom,
        Specialty,
        Subject,
        SubjectAssignment,
        Term,
    )
    from apps.people.models import StudentProfile

    year = academic_year
    if year is None:
        year = (
            AcademicYear.objects.filter(school=school, is_active=True).first()
            or AcademicYear.objects.filter(school=school).order_by("-start_date").first()
        )
    if year is None:
        return {"created_assignments": 0, "skipped": "no_academic_year"}

    terms = list(Term.objects.filter(school=school, academic_year=year).order_by("position"))
    if not terms:
        return {"created_assignments": 0, "skipped": "no_terms"}

    pairs = list(
        StudentProfile.objects.filter(  # tenant-isolation-allow: scoped by school kwarg
            school=school, classroom__academic_year=year
        )
        .exclude(classroom__isnull=True)
        .exclude(specialty__isnull=True)
        .values_list("classroom_id", "specialty_id")
        .distinct()
    )
    if not pairs:
        return {"created_assignments": 0, "skipped": "no_enrolled_pairs"}

    classrooms = {c.id: c for c in Classroom.objects.filter(school=school, academic_year=year)}
    specialties = {s.id: s for s in Specialty.objects.filter(school=school)}
    all_subjects = list(Subject.objects.filter(school=school))

    created = 0
    with transaction.atomic():
        for classroom_id, specialty_id in pairs:
            classroom = classrooms.get(classroom_id)
            specialty = specialties.get(specialty_id)
            if classroom is None or specialty is None:
                continue
            subjects = resolve_specialty_subjects(school, specialty) or all_subjects
            for term in terms:
                if term.position == 3 and not classroom.allows_third_term:
                    continue
                for subject in subjects:
                    _, was_created = SubjectAssignment.objects.get_or_create(
                        academic_year=year,
                        term=term,
                        classroom=classroom,
                        specialty=specialty,
                        subject=subject,
                        defaults={"school": school},
                    )
                    created += 1 if was_created else 0
    return {"created_assignments": created, "pairs": len(pairs)}


def provision_country_baseline(
    school,
    *,
    academic_year: AcademicYear | None = None,
    school_type_codes: list[str] | None = None,
) -> dict[str, Any]:
    """THE single country-appropriate baseline provisioner.

    Both doors a school can enter through — self-service onboarding
    (``apps/schools/tasks.py``) and Migration-Cloud gap-fill
    (``apps/migration_cloud/post_apply_provision.py``) — converge here, so a
    school gets the SAME country-aware minimum baseline whichever way it arrived.
    Before this, each path hand-listed the same five-to-six calls in its own order
    and they had already drifted (year start month, whether terms/grading ran),
    which is exactly how a migrated school ended up with a mismatched calendar.

    Every step is idempotent (``ensure_*`` / ``get_or_create``) and everything it
    creates is a plain admin-editable row — a country DEFAULT, never a lock. The
    sequence:

      1. region fallback (``country_code`` → ``RegionConfig``) so downstream reads
         a real country pack rather than an empty ISO;
      2. academic year with a country-aware start month (unless the caller passes
         one it already created);
      3. the General department + specialty every ``FeePlan`` / ``SubjectAssignment``
         FK anchors on;
      4. the country/region Term structure (count + labels + dates);
      5. the country grading scale (+ default weights);
      6. cycle nodes + classrooms for the school's declared education type;
      7. the Classroom×Subject×Term teaching grid over whatever catalog exists.

    Returns a per-step summary dict. Best-effort per step: a single step failing is
    recorded in the summary, never raised — provisioning must never break the apply
    (or the signup) that called it.
    """
    if school is None:
        return {"skipped": "no_school"}

    summary: dict[str, Any] = {}

    # 1. Region fallback — a blank/unlinked country otherwise silently yields a
    #    generic 3-term structure with no country cycles.
    ensure_school_region(school)

    # 2. Academic year (country-aware start month). The caller may supply a year
    #    it already resolved (signup creates one inline; migration passes the row
    #    from its name-override path) — never override it.
    year = academic_year
    year_created = False
    if year is None:
        year, year_created = ensure_academic_year(school)
    if year is None:
        return {"skipped": "no_academic_year"}
    summary["academic_year"] = {"name": getattr(year, "name", ""), "created": bool(year_created)}

    # 3. Default department + specialty (fee-plan / subject-assignment FK anchors).
    summary["defaults"] = {
        "general_department": bool(ensure_general_department(school)),
        "general_specialty": bool(ensure_general_specialty(school)),
    }

    # 4. Country/region Term structure (Cameroon 3 trimesters, US 2 semesters, …).
    #    WITHOUT terms the teaching grid returns missing_prerequisites and no
    #    report card can be produced.
    summary["terms"] = ensure_terms(school, year)

    # 5. Country grading scale (+ default AssessmentWeights): Cameroon /20, US
    #    letter, etc. The report-card engine + mark entry both need one.
    try:
        from apps.evals.grading_provisioning import ensure_local_grading_scale

        ensure_local_grading_scale(school, academic_year=year)
        summary["grading_scale"] = True
    except Exception as exc:  # noqa: BLE001 — grading seed is best-effort
        logger.warning(
            "provision_country_baseline: grading scale failed for school %s: %s",
            getattr(school, "pk", "?"), exc, exc_info=True,
        )
        summary["grading_scale"] = f"error: {type(exc).__name__}"

    # 6. Cycle nodes + classrooms for the school's education type.
    summary["structure"] = provision_academic_structure_for_school(
        school,
        school_type_codes=school_type_codes,
        academic_year=year,
    )

    # 7. Country subject catalog — ONLY when the school has none (a roster-only
    #    export lands no subjects, so the grid would stay empty and no report card
    #    could be produced). An uploaded catalog always wins.
    summary["subjects"] = seed_country_subjects(school)

    # 7b. National subject codes on every code-less subject (seeded rows already
    #     carry one; this covers uploaded catalogs + pre-``code`` tenants).
    summary["subject_codes"] = backfill_subject_codes(school)

    # 7c. Country trade catalog for VOCATIONAL schools only (a TVET school lands
    #     with just "General" and nowhere to place a course of study). No-op for a
    #     general-ed school; skipped when trades were uploaded.
    summary["trades"] = seed_country_trades(school)

    # 7d. Country-default admission-number template (the country_defaults layer),
    #     applied per-tenant + guarded so it never changes a school that already
    #     issued numbers.
    summary["admission_template"] = ensure_admission_template(school)

    # 8. Teaching grid over the catalog (now non-empty for a general-ed school),
    #    idempotent either way.
    summary["teaching_grid"] = provision_teaching_grid_for_school(
        school, academic_year=year
    )

    # 9. Specialty↔subject curriculum + a STUDENT-DRIVEN per-specialty grid, so a
    #    student on a TVET trade (not "General") has matching assignments and is
    #    gradeable (Evaluation.clean requires the assignment's specialty to match
    #    the student's). Both idempotent + admin-editable.
    summary["curriculum"] = ensure_specialty_curriculum(school)
    summary["specialty_grid"] = provision_per_specialty_grid(school, academic_year=year)

    return summary
