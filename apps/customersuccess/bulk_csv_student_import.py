"""Wave R-E (v3.96.0 — 2026-05-26) — Bulk CSV student import kernel.

The new tenant's #1 friction point is "how do I get my 400 students into the
system without typing them by hand?". This kernel ships the parser +
validator + dry-run that the bulk-CSV onboarding wizard step calls.

Pure-function — no DB writes. The caller (the wizard's writer resolver)
loops the validated rows through ``StudentProfile.objects.create``.

Recognized header columns (case-insensitive, underscore-tolerant):

    Required: external_id, first_name, last_name
    Optional: middle_name, date_of_birth (YYYY-MM-DD), email,
              grade_level, guardian_email, guardian_name, guardian_phone

Per-row validation problems are collected into a result object — the
wizard surfaces them so the operator can fix the spreadsheet before
committing.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date as date_type


_REQUIRED_HEADERS = ("external_id", "first_name", "last_name")
_OPTIONAL_HEADERS = (
    "middle_name", "date_of_birth", "email",
    "grade_level", "guardian_email", "guardian_name", "guardian_phone",
)
_ALL_HEADERS = _REQUIRED_HEADERS + _OPTIONAL_HEADERS


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_EXT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MAX_NAME_LEN = 120


@dataclass
class CSVStudentRow:
    lineno: int
    external_id: str
    first_name: str
    last_name: str
    middle_name: str = ""
    date_of_birth: date_type | None = None
    email: str = ""
    grade_level: str = ""
    guardian_email: str = ""
    guardian_name: str = ""
    guardian_phone: str = ""

    def as_dict(self) -> dict:
        return {
            "lineno": self.lineno,
            "external_id": self.external_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "middle_name": self.middle_name,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else "",
            "email": self.email,
            "grade_level": self.grade_level,
            "guardian_email": self.guardian_email,
            "guardian_name": self.guardian_name,
            "guardian_phone": self.guardian_phone,
        }


@dataclass
class CSVRowError:
    lineno: int
    field: str
    reason: str
    raw_value: str = ""

    def as_dict(self) -> dict:
        return {
            "lineno": self.lineno, "field": self.field,
            "reason": self.reason, "raw_value": self.raw_value,
        }


@dataclass
class CSVValidationResult:
    rows: list[CSVStudentRow] = field(default_factory=list)
    errors: list[CSVRowError] = field(default_factory=list)
    duplicate_external_ids: list[str] = field(default_factory=list)
    detected_header_columns: list[str] = field(default_factory=list)
    rejected_header_columns: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.duplicate_external_ids

    @property
    def total_seen(self) -> int:
        return len(self.rows) + len(self.errors)

    def as_dict(self) -> dict:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "errors": [e.as_dict() for e in self.errors],
            "duplicate_external_ids": list(self.duplicate_external_ids),
            "detected_header_columns": list(self.detected_header_columns),
            "rejected_header_columns": list(self.rejected_header_columns),
            "is_valid": self.is_valid,
            "total_seen": self.total_seen,
        }


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_").replace("-", "_")


def _validate_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value or ""))


def _parse_date(raw: str) -> date_type | None:
    m = _DATE_RE.match((raw or "").strip())
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date_type(year, month, day)
    except ValueError:
        return None


def parse_and_validate_csv(text: str) -> CSVValidationResult:
    result = CSVValidationResult()
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        result.errors.append(
            CSVRowError(lineno=0, field="<header>", reason="empty_csv"),
        )
        return result

    normalized = [_normalize_header(h) for h in reader.fieldnames]
    result.detected_header_columns = list(normalized)
    accepted_idx: dict[str, int] = {}
    for i, header in enumerate(normalized):
        if header in _ALL_HEADERS:
            accepted_idx[header] = i
        else:
            result.rejected_header_columns.append(header)

    for req in _REQUIRED_HEADERS:
        if req not in accepted_idx:
            result.errors.append(
                CSVRowError(lineno=0, field=req, reason="required_header_missing"),
            )
    if result.errors:
        return result

    seen_external_ids: set[str] = set()
    dup_ids: set[str] = set()

    for raw_idx, raw_row in enumerate(reader, start=2):
        clean = {
            _normalize_header(k): (v or "").strip()
            for k, v in (raw_row or {}).items() if k is not None
        }

        # Skip wholly blank rows (Excel tail noise).
        if not any(clean.values()):
            continue

        line_errors: list[CSVRowError] = []

        ext_id = clean.get("external_id", "")
        if not ext_id:
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="external_id", reason="required",
            ))
        elif not _EXT_ID_RE.match(ext_id):
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="external_id",
                reason="invalid_format", raw_value=ext_id,
            ))
        else:
            if ext_id in seen_external_ids:
                dup_ids.add(ext_id)
            seen_external_ids.add(ext_id)

        first_name = clean.get("first_name", "")
        last_name = clean.get("last_name", "")
        if not first_name:
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="first_name", reason="required",
            ))
        if not last_name:
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="last_name", reason="required",
            ))
        if len(first_name) > _MAX_NAME_LEN or len(last_name) > _MAX_NAME_LEN:
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="name", reason="too_long",
            ))

        dob_value = None
        dob_raw = clean.get("date_of_birth", "")
        if dob_raw:
            dob_value = _parse_date(dob_raw)
            if dob_value is None:
                line_errors.append(CSVRowError(
                    lineno=raw_idx, field="date_of_birth",
                    reason="invalid_date_format_use_YYYY_MM_DD",
                    raw_value=dob_raw,
                ))

        email = clean.get("email", "")
        if email and not _validate_email(email):
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="email",
                reason="invalid_email", raw_value=email,
            ))

        guardian_email = clean.get("guardian_email", "")
        if guardian_email and not _validate_email(guardian_email):
            line_errors.append(CSVRowError(
                lineno=raw_idx, field="guardian_email",
                reason="invalid_email", raw_value=guardian_email,
            ))

        if line_errors:
            result.errors.extend(line_errors)
            continue

        result.rows.append(CSVStudentRow(
            lineno=raw_idx,
            external_id=ext_id,
            first_name=first_name,
            last_name=last_name,
            middle_name=clean.get("middle_name", "")[:_MAX_NAME_LEN],
            date_of_birth=dob_value,
            email=email,
            grade_level=clean.get("grade_level", "")[:40],
            guardian_email=guardian_email,
            guardian_name=clean.get("guardian_name", "")[:_MAX_NAME_LEN],
            guardian_phone=clean.get("guardian_phone", "")[:40],
        ))

    result.duplicate_external_ids = sorted(dup_ids)
    return result


@dataclass
class BulkImportApplyResult:
    created: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


def apply_bulk_csv(
    *,
    school_id: int,
    validated: CSVValidationResult,
    db_runner=None,
) -> BulkImportApplyResult:
    """Apply a validated batch. ``db_runner`` swaps for tests.

    The default runner skips creating rows whose ``external_id`` is already
    present so re-running the wizard is idempotent.
    """
    if not validated.is_valid:
        return BulkImportApplyResult(
            errors=[{"reason": "validation_failed", "count": len(validated.errors)}],
        )
    runner = db_runner or _default_db_runner
    return runner(school_id=school_id, rows=list(validated.rows))


def _student_code_for_import(*, school_id: int, external_id: str) -> str:
    """Map CSV external_id to a tenant-scoped student_code (global unique constraint)."""
    prefix = f"S{school_id}-"
    return f"{prefix}{external_id}"[:50]


def _default_db_runner(*, school_id: int, rows: list[CSVStudentRow]) -> BulkImportApplyResult:
    from apps.people.models import StudentProfile  # type: ignore

    result = BulkImportApplyResult()
    codes = [_student_code_for_import(school_id=school_id, external_id=r.external_id) for r in rows]
    # tenant-isolation-allow: bulk-csv-existing-set-confined-to-school-tenant
    existing = set(
        StudentProfile.objects.filter(school_id=school_id, student_code__in=codes).values_list(
            "student_code", flat=True
        )
    )
    for row, student_code in zip(rows, codes, strict=True):
        if student_code in existing:
            result.skipped += 1
            continue
        custom_attributes: dict[str, str] = {}
        if row.middle_name:
            custom_attributes["middle_name"] = row.middle_name
        if row.email:
            custom_attributes["email"] = row.email
        if row.grade_level:
            custom_attributes["grade_level"] = row.grade_level
        if row.guardian_email:
            custom_attributes["guardian_email"] = row.guardian_email
        if row.guardian_name:
            custom_attributes["guardian_name"] = row.guardian_name
        if row.guardian_phone:
            custom_attributes["guardian_phone"] = row.guardian_phone
        try:
            StudentProfile.objects.create(
                school_id=school_id,
                student_code=student_code,
                first_name=row.first_name,
                last_name=row.last_name,
                date_of_birth=row.date_of_birth,
                is_active=True,
                custom_attributes=custom_attributes,
            )
            result.created += 1
            existing.add(student_code)
        except Exception as exc:  # noqa: BLE001 — re-surfaced to caller
            result.errors.append(
                {"external_id": row.external_id, "reason": str(exc)[:240]},
            )
    return result
