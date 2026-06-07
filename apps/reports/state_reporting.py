"""State-reporting CSV exporter (Wave E — year-end governance).

Turns a tenant's enrolment data into a per-jurisdiction compliance packet (CSV),
entirely offline — no portal round-trip. Builds on the existing statutory
foundation (``platform_runtime.statutory_tenant_extract`` + ``apps/interop`` CEDS/
Ed-Fi scaffolds) by adding the concrete column mapping + CSV serialisation that
the register flagged as the gap.

``JURISDICTION_FORMATS`` is an extensible registry of starter column maps modelling
named frameworks (generic / Ed-Fi-style / CALPADS-style). They are honest column
mappings + CSV output, NOT certified state submissions — a real submission also
needs the authority's validation rules + transport, which layer on top.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave E) and register row ``state-reporting-bridges``.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Callable


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


# Each format: ordered list of (CSV header, extractor(student) -> str).
JURISDICTION_FORMATS: dict[str, list[tuple[str, Callable[[Any], str]]]] = {
    "GENERIC": [
        ("StudentID", lambda s: s.student_code or ""),
        ("LastName", lambda s: s.last_name or ""),
        ("FirstName", lambda s: s.first_name or ""),
        ("DateOfBirth", lambda s: _iso(getattr(s, "date_of_birth", None))),
        ("Gender", lambda s: getattr(s, "gender", "") or ""),
        ("EnrollmentStatus", lambda s: getattr(s, "status", "") or ""),
        ("EnrollmentDate", lambda s: _iso(getattr(s, "joined_date", None))),
    ],
    # Ed-Fi-style (US federal EDFacts lineage) — subset of common elements.
    "US_EDFACTS": [
        ("StudentUniqueId", lambda s: s.student_code or ""),
        ("LastSurname", lambda s: s.last_name or ""),
        ("FirstName", lambda s: s.first_name or ""),
        ("BirthDate", lambda s: _iso(getattr(s, "date_of_birth", None))),
        ("Sex", lambda s: getattr(s, "gender", "") or ""),
        ("EntryDate", lambda s: _iso(getattr(s, "joined_date", None))),
    ],
    # California CALPADS-style — SSID + enrollment.
    "CA_CALPADS": [
        ("SSID", lambda s: s.student_code or ""),
        ("StudentLegalLastName", lambda s: s.last_name or ""),
        ("StudentLegalFirstName", lambda s: s.first_name or ""),
        ("StudentBirthDate", lambda s: _iso(getattr(s, "date_of_birth", None))),
        ("StudentGenderCode", lambda s: (getattr(s, "gender", "") or "")[:1].upper()),
        ("EnrollmentStatusCode", lambda s: getattr(s, "status", "") or ""),
    ],
}

DEFAULT_JURISDICTION = "GENERIC"


def available_jurisdictions() -> list[str]:
    return sorted(JURISDICTION_FORMATS)


def build_state_report_rows(school_id, jurisdiction: str = DEFAULT_JURISDICTION) -> list[dict[str, str]]:
    """Ordered, jurisdiction-shaped rows for every student in the school."""
    from apps.people.models import StudentProfile

    spec = JURISDICTION_FORMATS.get(jurisdiction) or JURISDICTION_FORMATS[DEFAULT_JURISDICTION]
    rows: list[dict[str, str]] = []
    for student in StudentProfile.objects.filter(school_id=school_id).order_by("last_name", "first_name"):
        rows.append({header: extract(student) for header, extract in spec})
    return rows


def export_state_report_csv(school_id, jurisdiction: str = DEFAULT_JURISDICTION) -> str:
    """Return a CSV compliance packet (header + one row per student)."""
    spec = JURISDICTION_FORMATS.get(jurisdiction) or JURISDICTION_FORMATS[DEFAULT_JURISDICTION]
    headers = [h for h, _ in spec]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in build_state_report_rows(school_id, jurisdiction):
        writer.writerow(row)
    return buf.getvalue()
