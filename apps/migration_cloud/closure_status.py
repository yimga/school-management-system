"""Aggregate post-import closure readiness for one tenant."""

from __future__ import annotations

from typing import Any, Optional

from apps.migration_cloud.catalog_repair import plan_inverted_catalog_repair
from apps.migration_cloud.finance_ledger import assess_finance_ledger_readiness
from apps.migration_cloud.teaching_graph import assess_teaching_graph_readiness


def assess_people_directory_readiness(school) -> dict[str, Any]:
    """Counts enrollment SOT + guardian directory coverage."""
    from apps.metadata.models import DynamicFieldValue
    from apps.people.models import Enrollment, StudentGuardian, StudentProfile

    if school is None:
        return {"ready": False, "reason": "no_school"}

    active_students = StudentProfile.objects.filter(school=school, is_active=True)
    total_active = active_students.count()
    active_enrollments = Enrollment.objects.filter(
        school=school,
        status=Enrollment.Status.ACTIVE,
    ).count()
    guardian_links = StudentGuardian.objects.filter(school=school).count()
    parent_hints = DynamicFieldValue.objects.filter(
        school=school,
        entity_type="student",
        field_key="parent_name",
    ).count()
    students_missing_active_enrollment = max(0, total_active - active_enrollments)

    return {
        "students_active": total_active,
        "active_enrollments": active_enrollments,
        "students_missing_active_enrollment": students_missing_active_enrollment,
        "guardian_links": guardian_links,
        "parent_name_hints": parent_hints,
        "ready_for_enrollment_sot": students_missing_active_enrollment == 0,
        "ready_for_guardian_directory": guardian_links > 0 or parent_hints == 0,
    }


def build_migration_closure_report(
    school,
    *,
    bundle=None,
) -> dict[str, Any]:
    """Single JSON-friendly snapshot for operator triage."""
    catalog = plan_inverted_catalog_repair(school)
    teaching = assess_teaching_graph_readiness(school)
    finance = assess_finance_ledger_readiness(school)
    people = assess_people_directory_readiness(school)

    quarantine: dict[str, Any] = {"bundle_id": None, "held_rows_pending": 0}
    if bundle is not None:
        from apps.migration_cloud.quarantine_profile import profile_quarantine_distribution

        profile = profile_quarantine_distribution(bundle, pending_only=True)
        quarantine = {
            "bundle_id": bundle.pk,
            "held_rows_pending": profile.get("total", 0),
            "pdf_noise_candidates": profile.get("pdf_noise_candidates", 0),
            "by_issue_class": profile.get("by_issue_class", {}),
            "by_domain": profile.get("by_domain", {}),
        }

    playbook_ready = (
        not catalog.get("actionable")
        and teaching.get("ready_for_grades")
        and finance.get("ready")
        and people.get("ready_for_enrollment_sot")
        and quarantine.get("held_rows_pending", 0) == 0
    )

    return {
        "school": getattr(school, "slug", None) or str(school),
        "catalog": {
            "actionable": catalog.get("actionable", False),
            "phantom_specialties": len(catalog.get("phantom_specialties_removed", [])),
            "phantom_departments": len(catalog.get("phantom_departments_removed", [])),
        },
        "teaching_graph": teaching,
        "people_directory": people,
        "finance_ledger": finance,
        "quarantine": quarantine,
        "playbook_ready": playbook_ready,
    }
