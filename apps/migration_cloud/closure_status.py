"""Aggregate post-import closure readiness for one tenant."""

from __future__ import annotations

from typing import Any

from apps.migration_cloud.catalog_repair import plan_inverted_catalog_repair
from apps.migration_cloud.finance_ledger import assess_finance_ledger_readiness
from apps.migration_cloud.teaching_graph import assess_teaching_graph_readiness


def assess_grades_readiness(school) -> dict[str, Any]:
    """Whether evaluation rows exist for gradebook / report-card surfaces."""
    if school is None:
        return {"ready": False, "reason": "no_school"}
    try:
        from apps.evals.models import Evaluation

        evaluation_count = Evaluation.objects.filter(school=school).count()
    except ImportError:
        return {"evaluation_rows": 0, "ready_for_gradebook": False}
    return {
        "evaluation_rows": evaluation_count,
        "ready_for_gradebook": evaluation_count > 0,
    }


def assess_bundle_import_alignment(bundle) -> dict[str, Any]:
    """Detection + apply alignment for one bundle (mis-tag / stale apply)."""
    if bundle is None:
        return {"bundle_id": None, "needs_reimport": False, "apply_totals": {}}
    from apps.migration_cloud.retag_reimport import bundle_needs_reimport_after_retag

    totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    per_domain = totals.get("by_domain") or totals.get("per_domain") or {}
    return {
        "bundle_id": bundle.pk,
        "status": str(getattr(bundle, "status", "") or ""),
        "needs_reimport": bundle_needs_reimport_after_retag(bundle),
        "apply_totals": {
            "created": int(totals.get("created") or 0),
            "updated": int(totals.get("updated") or 0),
            "quarantined": int(totals.get("quarantined") or 0),
            "by_domain": per_domain,
        },
    }


def assess_classroom_roster_health(school, *, classroom_name: str = "") -> dict[str, Any]:
    """Spot-check classroom rosters (e.g. Form One) for operator acceptance."""
    if school is None:
        return {"classrooms": 0, "sample_roster": None}
    from apps.academics.models import Classroom
    from apps.people.models import StudentProfile

    qs = Classroom.objects.filter(school=school)
    if classroom_name:
        qs = qs.filter(name__icontains=classroom_name)
    sample = qs.order_by("name").first()
    if sample is None:
        return {
            "classrooms": Classroom.objects.filter(school=school).count(),
            "sample_roster": None,
            "sample_classroom_name": classroom_name or None,
        }
    roster_count = StudentProfile.objects.filter(
        school=school, is_active=True, classroom=sample
    ).count()
    return {
        "classrooms": Classroom.objects.filter(school=school).count(),
        "sample_roster": roster_count,
        "sample_classroom_name": sample.name,
        "sample_classroom_id": sample.pk,
    }


def build_import_graph_health_report(
    school,
    *,
    bundle=None,
    classroom_probe: str = "",
) -> dict[str, Any]:
    """Definition-of-done layers for import → grades graph closure."""
    from apps.people.models import TeacherProfile

    base = build_migration_closure_report(school, bundle=bundle)
    bundle_align = assess_bundle_import_alignment(bundle)
    grades = assess_grades_readiness(school)
    roster = assess_classroom_roster_health(school, classroom_name=classroom_probe)
    teachers = TeacherProfile.objects.filter(school=school).count() if school else 0

    layers = {
        "detection": {
            "ok": not bundle_align.get("needs_reimport"),
            "needs_reimport": bundle_align.get("needs_reimport"),
            "bundle_id": bundle_align.get("bundle_id"),
        },
        "reimport": {
            "ok": not bundle_align.get("needs_reimport"),
            "bundle_status": bundle_align.get("status"),
        },
        "people": {
            "ok": teachers > 0 or base["people_directory"]["students_active"] == 0,
            "teachers": teachers,
            "students_active": base["people_directory"]["students_active"],
        },
        "placement": {
            "ok": base["teaching_graph"]["students_missing_classroom"] == 0,
            "missing_classroom": base["teaching_graph"]["students_missing_classroom"],
            "gradeable_students": base["teaching_graph"]["students_with_class_and_specialty"],
        },
        "enrollment": {
            "ok": base["people_directory"]["ready_for_enrollment_sot"],
            "active_enrollments": base["people_directory"]["active_enrollments"],
            "students_active": base["people_directory"]["students_active"],
        },
        "teaching_graph": {
            "ok": base["teaching_graph"]["ready_for_grades"],
            "subject_assignments": base["teaching_graph"]["subject_assignments"],
            "teacher_assignments": base["teaching_graph"]["teacher_assignments_active"],
        },
        "grades": {
            "ok": grades["ready_for_gradebook"],
            "evaluation_rows": grades["evaluation_rows"],
            "note": (
                "No evaluation rows yet — import grades or enter marks if expected."
            ),
        },
        "classroom_probe": roster,
    }

    graph_ready = all(
        layer.get("ok")
        for key, layer in layers.items()
        if key not in ("grades", "classroom_probe")
    )
    # Grades are optional unless the bundle applied a grades domain.
    applied_domains = bundle_align.get("apply_totals", {}).get("by_domain") or {}
    grades_expected = any(
        str(domain).startswith("grade") or domain in ("evaluations", "marks", "grades")
        for domain in applied_domains
    )
    if grades_expected and not layers["grades"]["ok"]:
        graph_ready = False

    return {
        **base,
        "bundle_alignment": bundle_align,
        "grades": grades,
        "import_graph_layers": layers,
        "import_graph_ready": graph_ready and base["playbook_ready"],
    }


def evaluate_import_closure_findings(report: dict[str, Any]) -> list[str]:
    """Human-readable gaps for ``verify_tenant_import_closure --strict``."""
    findings: list[str] = []
    layers = report.get("import_graph_layers") or {}
    for name, layer in layers.items():
        if name == "classroom_probe":
            continue
        if not isinstance(layer, dict):
            continue
        if layer.get("ok"):
            continue
        if name == "detection" or name == "reimport":
            findings.append(
                "Record types were corrected but bundle still needs re-import "
                f"(bundle_id={layer.get('bundle_id')})"
            )
        elif name == "people":
            findings.append(
                f"No teachers landed ({layer.get('teachers', 0)} teachers, "
                f"{layer.get('students_active', 0)} students)"
            )
        elif name == "placement":
            findings.append(
                f"{layer.get('missing_classroom', 0)} active student(s) missing classroom"
            )
        elif name == "enrollment":
            findings.append(
                f"Enrollment SOT gap: {layer.get('active_enrollments', 0)}/"
                f"{layer.get('students_active', 0)} active enrollments"
            )
        elif name == "teaching_graph":
            findings.append(
                "Teaching graph not ready for grades "
                f"(subject_assignments={layer.get('subject_assignments', 0)}, "
                f"teacher_assignments={layer.get('teacher_assignments', 0)})"
            )
        elif name == "grades":
            findings.append(
                f"Grades expected but no evaluation rows ({layer.get('evaluation_rows', 0)})"
            )

    quarantine = report.get("quarantine") or {}
    held = int(quarantine.get("held_rows_pending") or 0)
    if held:
        findings.append(f"{held} held row(s) still pending in bundle")

    catalog = report.get("catalog") or {}
    if catalog.get("actionable"):
        findings.append("Academic catalog inversion still actionable")

    finance = report.get("finance_ledger") or {}
    if finance.get("ready") is False:
        findings.append("Finance ledger closure not ready")

    return findings


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
