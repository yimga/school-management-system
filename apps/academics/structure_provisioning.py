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


def _slug_code(prefix: str, label: str, idx: int) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in label.lower())[:20]
    return f"{prefix}-{base}-{idx}"[:30]


def ensure_general_department(school):
    """Return the single canonical "General" department for ``school``.

    Idempotent and the SOLE creator of the default department. The academic-
    structure provisioner and the Phase-B classroom seeder both need a home
    department; before this they each created their OWN "General" dept with a
    different globally-unique code (``GEN-<id8>`` vs ``<slug>-GEN``), leaving
    every freshly provisioned tenant with two identically-named departments.
    Resolves by canonical code, then adopts any pre-existing same-named
    department (tenants seeded before this fix), else creates one.
    """
    if school is None:
        return None
    canonical_code = f"GEN-{str(school.id)[:8]}"
    dept = Department.objects.filter(school=school, code=canonical_code).first()
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
    return Department.objects.create(
        school=school,
        code=canonical_code,
        name="General",
    )


def ensure_general_specialty(school):
    """Return the single canonical "General" specialty for ``school``.

    Idempotent, and the SOLE creator of the default specialty. Nothing in
    provisioning created a Specialty at all, which quietly made a "COMPLETED"
    tenant unusable: ``FeePlan.specialty`` is a non-null FK, so no fee plan could
    be created (the automated fee task just returns ``{"status": "no_plans"}`` as
    SUCCESS), and ``SubjectAssignment.specialty`` is non-null too, so the entire
    teaching grid was unbuildable — a day-1 teacher opened the classroom dropdown
    and saw nothing, with no error to explain why.

    ``Specialty.code`` is GLOBALLY unique (max_length=30), NOT unique-per-school,
    so the code MUST be namespaced by school id — exactly the trap documented on
    ``Classroom.code`` below, where two schools sharing a pack school_type
    collided and the SECOND school's provisioning died on a UNIQUE violation.
    Mirrors ``ensure_general_department``: resolve by canonical code, adopt any
    pre-existing same-named row, else create.
    """
    if school is None:
        return None
    from apps.academics.models import Specialty

    canonical_code = f"SPEC-GEN-{str(school.id)[:8]}"[:30]
    specialty = Specialty.objects.filter(school=school, code=canonical_code).first()
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
            Term.objects.filter(pk=first.pk).update(is_active=True)
    return {"created_terms": created, "term_count": term_count}


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
                # Classroom.code is GLOBALLY unique (max_length=30), so the seed
                # code MUST be namespaced by school id — otherwise two schools
                # sharing a pack school_type (e.g. two US "high" schools) generate
                # the same code and the SECOND school's provisioning dies with a
                # UNIQUE collision (the "provisioning fails for the next school"
                # bug). Mirrors the school-scoped dept_code above.
                sid = str(getattr(school, "id", "")).replace("-", "")[:8]
                room_code = _slug_code(f"{sid}-{code}", label, 0)
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

    from apps.academics.country_subject_codes import resolve_subject_code

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
                defaults={"category": category, "code": resolve_subject_code(school, name)},
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
    from apps.academics.country_subject_codes import resolve_subject_code
    from apps.academics.models import Subject

    coded = 0
    for subject in Subject.objects.filter(school=school).filter(code=""):
        code = resolve_subject_code(school, subject.name)
        if not code:
            continue
        try:
            Subject.objects.filter(pk=subject.pk).update(code=code)
            coded += 1
        except Exception:  # noqa: BLE001 — one subject never aborts the rest
            logger.debug("backfill_subject_codes: subject %s failed", subject.name, exc_info=True)
    return {"coded_subjects": coded}


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

    # 8. Teaching grid over the catalog (now non-empty for a general-ed school),
    #    idempotent either way.
    summary["teaching_grid"] = provision_teaching_grid_for_school(
        school, academic_year=year
    )

    return summary
