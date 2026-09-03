"""Post-import academic catalog repair — CM TVET inversion and phantom cleanup.

Extracted from ``remediate_inverted_academic_catalog`` so autopilot and CLI share
one implementation.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction


def plan_inverted_catalog_repair(school) -> dict[str, Any]:
    """Detect phantom departments/specialties that duplicate real subjects."""
    from apps.academics.models import Department, Specialty, Subject

    subject_names = set(
        Subject.objects.filter(school=school).values_list("name", flat=True)
    )
    plan: dict[str, Any] = {
        "subjects_promoted_from_departments": [],
        "phantom_specialties_removed": [],
        "phantom_departments_removed": [],
        "curriculum_links_created": 0,
        "actionable": False,
    }

    for dept in Department.objects.filter(school=school).values("id", "name"):
        name = dept["name"]
        if name in subject_names:
            plan["phantom_departments_removed"].append(name)
        elif Subject.objects.filter(school=school, name__iexact=name).exists():
            plan["subjects_promoted_from_departments"].append(name)

    for sp in Specialty.objects.filter(school=school).values("id", "name"):
        name = sp["name"]
        if name in subject_names:
            plan["phantom_specialties_removed"].append(name)
        elif Subject.objects.filter(school=school, name__iexact=name).exists():
            plan["phantom_specialties_removed"].append(name)

    plan["actionable"] = bool(
        plan["phantom_specialties_removed"]
        or plan["phantom_departments_removed"]
        or plan["subjects_promoted_from_departments"]
    )
    return plan


def apply_inverted_catalog_repair(school) -> dict[str, Any]:
    """Remove safe phantom catalog rows and ensure curriculum links."""
    from apps.academics.models import Department, Specialty, SpecialtySubject, Subject
    from apps.academics.structure_provisioning import ensure_specialty_curriculum
    from apps.people.models import StudentProfile, TeacherProfile

    subject_names = set(
        Subject.objects.filter(school=school).values_list("name", flat=True)
    )
    removed_specs = 0
    removed_depts = 0

    with transaction.atomic():
        for sp in Specialty.objects.filter(school=school).values("id", "name"):
            sp_id = sp["id"]
            name = sp["name"]
            if name not in subject_names and not Subject.objects.filter(
                school=school, name__iexact=name
            ).exists():
                continue
            if StudentProfile.objects.filter(school=school, specialty_id=sp_id).exists():
                continue
            SpecialtySubject.objects.filter(
                school=school, specialty_id=sp_id
            ).delete()
            Specialty.objects.filter(pk=sp_id).delete()
            removed_specs += 1

        for dept in Department.objects.filter(school=school).values("id", "name"):
            dept_id = dept["id"]
            name = dept["name"]
            if name not in subject_names:
                continue
            if name.lower() == "general":
                continue
            if TeacherProfile.objects.filter(school=school, department_id=dept_id).exists():
                continue
            if Specialty.objects.filter(school=school, department_id=dept_id).exists():
                continue
            if StudentProfile.objects.filter(
                school=school, specialty__department_id=dept_id
            ).exists():
                continue
            Department.objects.filter(pk=dept_id).delete()
            removed_depts += 1

        summary = ensure_specialty_curriculum(school)
        links = int(summary.get("created_links") or 0)

    return {
        "phantom_specialties_removed": removed_specs,
        "phantom_departments_removed": removed_depts,
        "curriculum_links_created": links,
    }


def school_wants_catalog_autorepair(school) -> bool:
    """True for Cameroon TVET schools where inversion is a known failure mode."""
    if not school:
        return False
    country = str(getattr(school, "country_code", "") or "").upper()
    if country in {"CM", "CMR", "CAMEROON"}:
        return True
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return False
    grading = settings.get("grading") or {}
    tracks = grading.get("curriculum_tracks") or settings.get("curriculum_tracks") or []
    if isinstance(tracks, str):
        tracks = [tracks]
    return "vocational_trade" in {str(t).lower() for t in tracks}


def auto_repair_inverted_catalog_for_school(school, *, dry_run: bool = False) -> dict[str, Any]:
    """Detect and optionally apply catalog inversion repair for one tenant."""
    plan = plan_inverted_catalog_repair(school)
    result = {"plan": plan, "applied": False}
    if not plan.get("actionable"):
        return result
    if dry_run:
        return result
    applied = apply_inverted_catalog_repair(school)
    result["applied"] = True
    result.update(applied)
    return result
