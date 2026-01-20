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


REQUIRED_HEADERS = [
    "student_code",
    "subject_assignment_id",
    "term_id",
    "teacher_username",
    "seq1",
    "seq2",
    "exam",
    "mock",
    "practical",
    "remarks",
]


@dataclass
class GradeImportRow:
    student_code: str
    subject_assignment_id: int
    term_id: int
    teacher_username: str
    seq1: float
    seq2: float
    exam: float
    mock: float
    practical: float
    remarks: str
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
                subject_assignment_id=int(raw["subject_assignment_id"]),
                term_id=int(raw["term_id"]),
                teacher_username=str(raw.get("teacher_username") or "").strip(),
                seq1=float(raw.get("seq1") or 0),
                seq2=float(raw.get("seq2") or 0),
                exam=float(raw.get("exam") or 0),
                mock=float(raw.get("mock") or 0),
                practical=float(raw.get("practical") or 0),
                remarks=str(raw.get("remarks") or "").strip(),
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
    Term = django_apps.get_model("academics", "Term")
    TeacherProfile = django_apps.get_model("people", "TeacherProfile")
    StudentProfile = django_apps.get_model("people", "StudentProfile")

    created = 0
    updated = 0

    for row in preview.rows:
        student = StudentProfile.objects.filter(student_code=row.student_code).first()
        assignment = SubjectAssignment.objects.filter(
            id=row.subject_assignment_id,
            academic_year=academic_year,
        ).select_related("classroom").first()
        term = Term.objects.filter(id=row.term_id).first()
        teacher = None
        if row.teacher_username:
            teacher = TeacherProfile.objects.filter(user__username=row.teacher_username).first()
        if not student or not assignment or not term:
            continue
        obj, was_created = Evaluation.objects.update_or_create(
            student=student,
            subject_assignment=assignment,
            term=term,
            defaults={
                "academic_year": academic_year,
                "teacher": teacher or assignment.teacher if hasattr(assignment, "teacher") else None,
                "seq1_score": row.seq1,
                "seq2_score": row.seq2,
                "exam_score": row.exam,
                "mock_score": row.mock,
                "practical_score": row.practical,
                "remarks": row.remarks,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}
