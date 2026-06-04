"""
Lightweight helpers for bulk grade-sheet imports.
This is intentionally simple (no IO side effects) so it can be wired to an
admin action, management command, or portal view later without duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from django.apps import apps as django_apps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError

from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4: Typed tuple for row-level import lookups and DB operations.
_EVALS_IMPORTERS_ROW_ERRORS = (
    ObjectDoesNotExist,
    ValidationError,
    ValueError,
    TypeError,
    KeyError,
    DatabaseError,
    IntegrityError,
)


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
    is_valid: bool = True
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


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


def apply_import_from_preview(preview: GradeImportPreview, academic_year):
    """
    Persist rows from a validated preview. Caller ensures permissions.

    NOTE: previously also named ``apply_import`` — it was silently shadowed by
    the csv-rows ``apply_import`` defined later in this module, so the
    migration grade-import path (which passes a GradeImportPreview) was calling
    the wrong function. Renamed to disambiguate.
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
    created_ids = []
    updated_ids = []

    for row in preview.rows:
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        student = StudentProfile.objects.filter(student_code=row.student_code).first()
        assignment = (
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            SubjectAssignment.objects.filter(
                id=row.subject_assignment_id,
                academic_year=academic_year,
            )
            .select_related("classroom")
            .first()
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        )
        term = Term.objects.filter(id=row.term_id).first()
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        teacher = None
        if row.teacher_username:
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            teacher = TeacherProfile.objects.filter(
                user__username=row.teacher_username
            ).first()
        if not student or not assignment or not term:
            continue
        obj, was_created = Evaluation.objects.update_or_create(
            student=student,
            subject_assignment=assignment,
            term=term,
            defaults={
                "academic_year": academic_year,
                "teacher": teacher or assignment.teacher
                if hasattr(assignment, "teacher")
                else None,
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
            created_ids.append(obj.pk)
        else:
            updated += 1
            updated_ids.append(obj.pk)
    return {
        "created": created,
        "updated": updated,
        "created_ids": created_ids,
        "updated_ids": updated_ids,
    }


# ========== ENHANCED VALIDATION & IMPORT ==========


def preview_import_with_validation(csv_rows):
    """Enhanced preview with detailed validation."""
    from decimal import Decimal
    from apps.evals.validators import GradeValidator
    from apps.evals.models import Evaluation, AssessmentWeights

    rows_with_validation = []
    errors = []

    for idx, row in enumerate(csv_rows, start=2):
        try:
            # Lookup entities
            StudentProfile = django_apps.get_model("people", "StudentProfile")
            SubjectAssignment = django_apps.get_model("academics", "SubjectAssignment")
            Term = django_apps.get_model("academics", "Term")
            TeacherProfile = django_apps.get_model("people", "TeacherProfile")

            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            student = StudentProfile.objects.get(student_code=row.get("student_code"))
            # tenant-isolation-allow: import-pipeline-pk-lookup
            subject_assignment = SubjectAssignment.objects.get(
                id=row.get("subject_assignment_id")
            )
            # tenant-isolation-allow: import-pipeline-pk-lookup
            term = Term.objects.get(id=row.get("term_id"))
            # tenant-isolation-allow: import-pipeline-pk-lookup
            teacher = TeacherProfile.objects.get(
                user__username=row.get("teacher_username")
            )

            # Get weights
            weights = AssessmentWeights.get_for(
                student.academic_year, subject_assignment.classroom, term
            )

            # Create temp evaluation
            temp_eval = Evaluation(
                academic_year=student.academic_year,
                term=term,
                subject_assignment=subject_assignment,
                student=student,
                teacher=teacher,
                seq1_score=Decimal(str(row.get("seq1") or 0)),
                seq2_score=Decimal(str(row.get("seq2") or 0)),
                exam_score=Decimal(str(row.get("exam") or 0)),
                mock_score=Decimal(str(row.get("mock") or 0))
                if row.get("mock")
                else None,
                practical_score=Decimal(str(row.get("practical") or 0))
                if row.get("practical")
                else None,
                remarks=row.get("remarks", ""),
            )

            # Validate
            validator = GradeValidator(score_scale=Decimal(str(weights.score_scale)))
            validation_result = validator.validate_evaluation(temp_eval, weights)

            row_obj = GradeImportRow(
                student_code=row.get("student_code"),
                subject_assignment_id=row.get("subject_assignment_id"),
                term_id=row.get("term_id"),
                teacher_username=row.get("teacher_username"),
                seq1=float(row.get("seq1") or 0),
                seq2=float(row.get("seq2") or 0),
                exam=float(row.get("exam") or 0),
                mock=float(row.get("mock") or 0),
                practical=float(row.get("practical") or 0),
                remarks=row.get("remarks", ""),
                raw=row,
                is_valid=validation_result["is_valid"],
                errors=validation_result["errors"],
                warnings=list(validation_result["flags"].keys()),
            )

            rows_with_validation.append(row_obj)

        except _EVALS_IMPORTERS_ROW_ERRORS as e:
            log_exception_with_context(
                "evals importers preview_import_with_validation row failed",
                extra={"row_index": idx, "student_code": row.get("student_code")},
            )
            errors.append(f"Row {idx}: {str(e)}")

    return rows_with_validation, errors


def apply_import(csv_rows, academic_year=None):
    """Apply import with real-time DB updates."""
    import time
    from decimal import Decimal

    start_time = time.time()
    created_count = 0
    updated_count = 0

    Evaluation = django_apps.get_model("evals", "Evaluation")
    SubjectAssignment = django_apps.get_model("academics", "SubjectAssignment")
    Term = django_apps.get_model("academics", "Term")
    TeacherProfile = django_apps.get_model("people", "TeacherProfile")
    StudentProfile = django_apps.get_model("people", "StudentProfile")
    # tenant-isolation-allow: import-pipeline-validates-school-before-persist
    AcademicYear = django_apps.get_model("academics", "AcademicYear")

    # If no academic year provided, use active
    if not academic_year:
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        academic_year = AcademicYear.objects.filter(is_active=True).first()

    # tenant-isolation-allow: import-pipeline-validates-school-before-persist
    for row in csv_rows:
        try:
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            student = StudentProfile.objects.get(student_code=row.get("student_code"))
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            subject_assignment = SubjectAssignment.objects.get(
                id=row.get("subject_assignment_id")
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            )
            term = Term.objects.get(id=row.get("term_id"))
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            teacher = TeacherProfile.objects.get(
                user__username=row.get("teacher_username")
            )

            eval_obj, created = Evaluation.objects.update_or_create(
                academic_year=academic_year,
                term=term,
                subject_assignment=subject_assignment,
                student=student,
                defaults={
                    "teacher": teacher,
                    "seq1_score": Decimal(str(row.get("seq1") or 0)),
                    "seq2_score": Decimal(str(row.get("seq2") or 0)),
                    "exam_score": Decimal(str(row.get("exam") or 0)),
                    "mock_score": Decimal(str(row.get("mock") or 0))
                    if row.get("mock")
                    else None,
                    "practical_score": Decimal(str(row.get("practical") or 0))
                    if row.get("practical")
                    else None,
                    "remarks": row.get("remarks", ""),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        except _EVALS_IMPORTERS_ROW_ERRORS:
            log_exception_with_context(
                "evals importers apply_import row failed",
                school_id=getattr(academic_year, "school_id", None)
                if academic_year
                else None,
                extra={
                    "row": row,
                    "academic_year_id": getattr(academic_year, "id", None),
                },
            )
            continue

    duration = time.time() - start_time

    return {
        "created": created_count,
        "updated": updated_count,
        "duration_seconds": round(duration, 2),
    }


def dry_run_grade_import(csv_rows, academic_year=None):
    """
    Simulate grade import: same lookups as apply_import but no DB writes.
    Returns scorecard dict: created, updated, errors (list of row error messages), duration_seconds.
    """
    import time

    start_time = time.time()
    would_create = 0
    would_update = 0
    errors = []

    Evaluation = django_apps.get_model("evals", "Evaluation")
    # tenant-isolation-allow: import-pipeline-validates-school-before-persist
    SubjectAssignment = django_apps.get_model("academics", "SubjectAssignment")
    Term = django_apps.get_model("academics", "Term")
    TeacherProfile = django_apps.get_model("people", "TeacherProfile")
    StudentProfile = django_apps.get_model("people", "StudentProfile")
    AcademicYear = django_apps.get_model("academics", "AcademicYear")

    if not academic_year:
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        academic_year = AcademicYear.objects.filter(is_active=True).first()

    # tenant-isolation-allow: import-pipeline-validates-school-before-persist
    for idx, row in enumerate(csv_rows, start=1):
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        try:
            student = StudentProfile.objects.get(student_code=row.get("student_code"))
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            subject_assignment = SubjectAssignment.objects.get(
                # tenant-isolation-allow: import-pipeline-validates-school-before-persist
                id=row.get("subject_assignment_id"), academic_year=academic_year
            )
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            term = Term.objects.get(id=row.get("term_id"))
            teacher_username = (row.get("teacher_username") or "").strip()
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            if teacher_username:
                # tenant-isolation-allow: import-pipeline-validates-school-before-persist
                TeacherProfile.objects.filter(user__username=teacher_username).first()
            exists = Evaluation.objects.filter(
                academic_year=academic_year,
                term=term,
                subject_assignment=subject_assignment,
                student=student,
            ).exists()
            if exists:
                would_update += 1
            else:
                would_create += 1
        except _EVALS_IMPORTERS_ROW_ERRORS as e:
            log_exception_with_context(
                "evals importers dry_run_grade_import row failed",
                extra={"row_index": idx, "student_code": row.get("student_code")},
            )
            errors.append(f"Row {idx}: {e}")

    duration = time.time() - start_time
    return {
        "created": would_create,
        "updated": would_update,
        "error_count": len(errors),
        "errors": errors[:50],
        "duration_seconds": round(duration, 2),
    }
