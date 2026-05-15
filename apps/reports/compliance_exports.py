"""
North Star SLICE 5 — regional compliance export registry and generation (download-only).

No external ministry submission; no fake approval. Returns CSV (or blocked) from real tenant data.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone as std_timezone
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.schools.tenant_access import safe_queryset_for_school

# --- Export family registry (static contract) ---

EXPORT_WAEC = "waec_wassce_student_summary"
EXPORT_OFSTED = "ofsted_school_summary"
EXPORT_MINISTRY = "ministry_student_report_summary"

_EXPORT_REGISTRY: dict[str, dict[str, Any]] = {
    EXPORT_WAEC: {
        "export_key": EXPORT_WAEC,
        "label": "WAEC / WASSCE student & report summary",
        "region_or_system": "West Africa (WAEC / WASSCE-style return)",
        "description": (
            "Tabular export of students and report-card rows for the selected academic year. "
            "Prepared for manual review or third-party tooling — not submitted automatically."
        ),
        "output_format": "text/csv",
        "required_data": [
            "school",
            "academic_year",
            "at_least_one_student",
            "at_least_one_report_card_for_year",
        ],
        "permission_required": "settings.manage",
        "template_family": "waec",
        "generated_filename_pattern": "{school_slug}_waec_wassce_student_summary_{date}.csv",
    },
    EXPORT_OFSTED: {
        "export_key": EXPORT_OFSTED,
        "label": "Ofsted-style school summary",
        "region_or_system": "United Kingdom (inspection-style summary)",
        "description": (
            "High-level school statistics: enrolment, staffing counts, report activity. "
            "Does not replace statutory returns; for local governance and planning only."
        ),
        "output_format": "text/csv",
        "required_data": [
            "school",
            "academic_year",
            "at_least_one_student",
        ],
        "permission_required": "settings.manage",
        "template_family": "ofsted",
        "generated_filename_pattern": "{school_slug}_ofsted_school_summary_{date}.csv",
    },
    EXPORT_MINISTRY: {
        "export_key": EXPORT_MINISTRY,
        "label": "Ministry-ready student / report summary",
        "region_or_system": "Generic ministry (CSV for manual filing)",
        "description": (
            "Consolidated student and report-card lines suitable for ministry-style reporting. "
            "Export only; your organization is responsible for official submission."
        ),
        "output_format": "text/csv",
        "required_data": [
            "school",
            "academic_year",
            "at_least_one_student",
            "at_least_one_report_card_for_year",
        ],
        "permission_required": "settings.manage",
        "template_family": "ministry",
        "generated_filename_pattern": "{school_slug}_ministry_student_report_summary_{date}.csv",
    },
}

ALL_EXPORT_KEYS: tuple[str, ...] = (
    EXPORT_WAEC,
    EXPORT_OFSTED,
    EXPORT_MINISTRY,
)


def _slug_date() -> str:
    return timezone.localdate().strftime("%Y-%m-%d")


def _safe_filename_part(s: str) -> str:
    s = (s or "school").strip() or "school"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:80]


def _years_scope_q(school) -> Q:
    """Tenant years plus shared/platform academic years (school FK nullable)."""
    return Q(school_id=school.pk) | Q(school_id__isnull=True)


def _resolve_academic_year_for_school(school, params: dict | None):
    """Return AcademicYear instance for school or None."""
    from apps.academics.models import AcademicYear

    params = params or {}
    scope = _years_scope_q(school)
    year_id = params.get("academic_year_id")
    if year_id is not None:
        try:
            yid = int(year_id)
        except (TypeError, ValueError):
            return None
        return (
            AcademicYear.objects.filter(pk=yid)
            .filter(scope)
            .order_by("-start_date")
            .first()
        )
    return (
        AcademicYear.objects.filter(scope)
        .order_by("-is_active", "-start_date")
        .first()
    )


def list_compliance_export_families(school) -> list[dict[str, Any]]:
    """Return one row per export family, including static metadata (tenant-agnostic fields)."""
    out: list[dict[str, Any]] = []
    for key in ALL_EXPORT_KEYS:
        base = dict(_EXPORT_REGISTRY[key])
        base["missing_data"] = get_compliance_export_missing_data(key, school)
        base["blocked"] = len(base["missing_data"]) > 0
        out.append(base)
    return out


def get_compliance_export_family(export_key: str) -> dict[str, Any] | None:
    if not export_key or export_key not in _EXPORT_REGISTRY:
        return None
    return dict(_EXPORT_REGISTRY[export_key])


def get_compliance_export_requirements(export_key: str, school) -> dict[str, Any]:
    """
    Structured requirements for UI. Keys are stable machine ids; values are human text.
    """
    fam = get_compliance_export_family(export_key)
    if not fam:
        return {}
    year = _resolve_academic_year_for_school(school, None)
    from apps.people.models import StudentProfile
    from apps.reports.models import ReportCard

    student_n = (
        safe_queryset_for_school(StudentProfile.objects.all(), school)
        .filter(is_active=True)
        .count()
        if school
        else 0
    )
    rc_n = 0
    if school and year:
        rc_n = (
            safe_queryset_for_school(ReportCard.objects.all(), school)
            .filter(academic_year_id=year.pk)
            .count()
        )

    return {
        "export_key": export_key,
        "school_present": bool(school),
        "academic_year_selected": year.pk if year else None,
        "academic_year_label": str(year) if year else None,
        "student_count_active": student_n,
        "report_card_count_for_year": rc_n,
        "required_fields_documentation": fam.get("required_data") or [],
        "permission_required": fam.get("permission_required"),
    }


def get_compliance_export_missing_data(
    export_key: str, school, params: dict | None = None
) -> list[str]:
    """Human-readable reasons blocking export (empty list => allowed)."""
    if export_key not in _EXPORT_REGISTRY:
        return ["Unknown export_key."]
    if school is None:
        return ["No tenant school on this request."]
    params = params or {}
    year = _resolve_academic_year_for_school(school, params)
    if year is None:
        return [
            "Define at least one academic year for this school (siteconfig academic-years evidence).",
        ]

    from apps.people.models import StudentProfile
    from apps.reports.models import ReportCard

    student_n = (
        safe_queryset_for_school(StudentProfile.objects.all(), school)
        .filter(is_active=True)
        .count()
    )
    if student_n < 1:
        return ["At least one active student profile is required for this export."]

    rc_n = (
        safe_queryset_for_school(ReportCard.objects.all(), school)
        .filter(academic_year_id=year.pk)
        .count()
    )

    if export_key in (EXPORT_WAEC, EXPORT_MINISTRY):
        if rc_n < 1:
            return [
                "No report cards found for the selected academic year. Generate report cards first.",
            ]

    if export_key == EXPORT_OFSTED:
        # Students already ensured; allow zero teachers but surface note in CSV
        return []

    return []


def _build_csv_waec_or_ministry(
    school,
    year,
    *,
    export_key: str,
) -> tuple[bytes, str]:
    from apps.reports.models import ReportCard

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "export_family",
            "school_name",
            "school_slug",
            "student_code",
            "student_first_name",
            "student_last_name",
            "academic_year",
            "report_card_type",
            "term_id",
            "report_generated_at",
            "language",
            "region_code",
        ]
    )
    qs = (
        ReportCard.objects.filter(school_id=school.pk, academic_year_id=year.pk)
        .select_related("student", "term")
        .order_by("student__student_code", "-generated_at")
    )
    for rc in qs[:5000]:
        st = rc.student
        writer.writerow(
            [
                export_key,
                school.name,
                school.slug,
                getattr(st, "student_code", "") or "",
                getattr(st, "first_name", "") or "",
                getattr(st, "last_name", "") or "",
                year.name,
                rc.type,
                rc.term_id or "",
                rc.generated_at.isoformat() if rc.generated_at else "",
                getattr(rc, "language", "") or "",
                getattr(rc, "region_code", "") or "",
            ]
        )
    payload = buffer.getvalue().encode("utf-8-sig")
    return payload, "text/csv; charset=utf-8"


def _build_csv_ofsted(school, year) -> tuple[bytes, str]:
    from apps.academics.models import Term
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.reports.models import ReportCard

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "metric",
            "value",
            "notes",
        ]
    )
    pupil_n = (
        safe_queryset_for_school(StudentProfile.objects.all(), school)
        .filter(is_active=True)
        .count()
    )
    staff_n = safe_queryset_for_school(
        TeacherProfile.objects.all(), school
    ).count()
    rc_n = (
        safe_queryset_for_school(ReportCard.objects.all(), school)
        .filter(academic_year_id=year.pk)
        .count()
    )
    term_n = Term.objects.filter(academic_year_id=year.pk).count()

    rows = [
        ("school_name", school.name, ""),
        ("school_slug", school.slug, ""),
        ("academic_year", year.name, ""),
        ("pupil_count_active", str(pupil_n), "Active student profiles"),
        ("teacher_count", str(staff_n), "Teacher profiles for school"),
        ("report_card_rows_for_year", str(rc_n), "ReportCard rows in scope"),
        ("term_rows_linked_to_year", str(term_n), ""),
        (
            "exported_at_utc",
            datetime.now(tz=std_timezone.utc).isoformat(),
            "Generation timestamp (UTC)",
        ),
    ]
    for r in rows:
        writer.writerow(r)
    payload = buffer.getvalue().encode("utf-8-sig")
    return payload, "text/csv; charset=utf-8"


def generate_regional_compliance_export(
    export_key: str,
    school,
    user,
    params: dict | None = None,
) -> dict[str, Any]:
    """
    Generate downloadable artifact or return a structured blocked payload.

    Success:
      { ok: True, content: bytes, content_type: str, filename: str, format: "csv" }

    Blocked:
      { ok: False, blocked: True, missing: [str], message: str }
    """
    params = params or {}
    missing = get_compliance_export_missing_data(export_key, school, params)
    if missing:
        return {
            "ok": False,
            "blocked": True,
            "missing": missing,
            "message": "Cannot generate export until requirements are satisfied.",
        }

    fam = get_compliance_export_family(export_key)
    if fam is None:
        raise ValueError(f"Unknown compliance export key: {export_key!r}")
    if school is None:
        raise ValueError("school is required for compliance export generation")
    year = _resolve_academic_year_for_school(school, params)
    if year is None:
        return {
            "ok": False,
            "blocked": True,
            "missing": ["Academic year could not be resolved."],
            "message": "Missing academic year.",
        }

    slug = _safe_filename_part(school.slug)
    date_part = _slug_date()

    if export_key == EXPORT_OFSTED:
        body, ctype = _build_csv_ofsted(school, year)
        fname = f"{slug}_ofsted_school_summary_{date_part}.csv"
        fmt = "csv"
    elif export_key == EXPORT_WAEC:
        body, ctype = _build_csv_waec_or_ministry(school, year, export_key=EXPORT_WAEC)
        fname = f"{slug}_waec_wassce_student_summary_{date_part}.csv"
        fmt = "csv"
    elif export_key == EXPORT_MINISTRY:
        body, ctype = _build_csv_waec_or_ministry(
            school, year, export_key=EXPORT_MINISTRY
        )
        fname = f"{slug}_ministry_student_report_summary_{date_part}.csv"
        fmt = "csv"
    else:
        return {
            "ok": False,
            "blocked": True,
            "missing": ["Unsupported export_key."],
            "message": "Unsupported export.",
        }

    # user is unused for row fabrication (audit happens in the view)
    _ = user

    return {
        "ok": True,
        "content": body,
        "content_type": ctype,
        "filename": fname,
        "format": fmt,
        "export_key": export_key,
        "academic_year_id": year.pk,
    }
