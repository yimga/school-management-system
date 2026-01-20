"""
Lightweight helpers for bulk grade-sheet imports.
This is intentionally simple (no IO side effects) so it can be wired to an
admin action, management command, or portal view later without duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError


REQUIRED_HEADERS = ["student_code", "subject_code", "term", "test1", "test2", "coef"]


@dataclass
class GradeImportRow:
    student_code: str
    subject_code: str
    term: str
    test1: float
    test2: float
    coef: float
    raw: dict


@dataclass
class GradeImportPreview:
    rows: List[GradeImportRow]
    errors: List[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _validate_headers(headers: Sequence[str]) -> List[str]:
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    return missing


def build_template_headers() -> List[str]:
    """
    Exportable helper so frontends can present the expected columns.
    """
    return list(REQUIRED_HEADERS)


def preview_import(data: Iterable[dict]) -> GradeImportPreview:
    """
    Takes an iterable of dict rows (e.g., parsed CSV) and returns a preview with
    row-level validation but no DB writes.
    """
    errors: List[str] = []
    rows: List[GradeImportRow] = []

    for idx, raw in enumerate(data, start=1):
        missing = _validate_headers(raw.keys())
        if missing:
            errors.append(f"Row {idx}: missing headers {missing}")
            continue
        try:
            row = GradeImportRow(
                student_code=str(raw["student_code"]).strip(),
                subject_code=str(raw["subject_code"]).strip(),
                term=str(raw["term"]).strip(),
                test1=float(raw.get("test1") or 0),
                test2=float(raw.get("test2") or 0),
                coef=float(raw.get("coef") or 1),
                raw=raw,
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {idx}: {exc}")
            continue
        rows.append(row)

    return GradeImportPreview(rows=rows, errors=errors)


def apply_import(preview: GradeImportPreview, academic_year):
    """
    Persist rows from a validated preview. Caller ensures permissions.
    """
    if not preview.is_valid:
        raise ValidationError("Preview contains errors; aborting import.")

    Evaluation = django_apps.get_model("evals", "Evaluation")
    SubjectAssignment = django_apps.get_model("academics", "SubjectAssignment")
    StudentProfile = django_apps.get_model("people", "StudentProfile")

    created = 0
    updated = 0

    for row in preview.rows:
        student = StudentProfile.objects.filter(student_code=row.student_code).first()
        assignment = SubjectAssignment.objects.filter(
            subject__code=row.subject_code,
            academic_year=academic_year,
        ).first()
        if not student or not assignment:
            continue
        obj, was_created = Evaluation.objects.update_or_create(
            student=student,
            subject_assignment=assignment,
            term=row.term,
            defaults={
                "continuous_assessment": row.test1,
                "exam_score": row.test2,
                "coefficient": row.coef if hasattr(Evaluation, "coefficient") else None,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}
