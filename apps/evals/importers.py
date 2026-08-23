"""
Lightweight helpers for bulk grade-sheet imports.
This is intentionally simple (no IO side effects) so it can be wired to an
admin action, management command, or portal view later without duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, List, Optional, Sequence

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
    # A blank sheet cell stays None (missing) rather than becoming 0.0 — see
    # _optional_decimal. Consumers write these straight onto the nullable
    # Evaluation score columns.
    seq1: Optional[float]
    seq2: Optional[float]
    exam: Optional[float]
    mock: Optional[float]
    practical: Optional[float]
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


def _optional_decimal(raw: Any) -> Optional[Decimal]:
    """A BLANK grade cell is a missing mark, not a mark of zero.

    ``or 0`` collapsed the two: a school importing sequence-1 marks in October
    leaves the exam column empty because the exam has not been sat, and every row
    landed with ``exam_score=0``. That reads as a genuine zero forever —
    ``is_complete_for_ranking`` then reports the class as fully marked and
    ``_apply_fill_missing`` (which only fills ``None`` components) will never
    touch it. Only an explicit "0" writes a zero.

    An unparseable cell is re-raised as ``ValueError`` because that is the type
    every guard on this pipeline is written against — ``preview_import``'s own
    ``except (ValueError, TypeError)``, ``_EVALS_IMPORTERS_ROW_ERRORS``, and the
    migration wizard's ``except`` in ``apps/accounts/views_migration.py``.
    ``Decimal("18,5")`` raises ``decimal.InvalidOperation``, an
    ``ArithmeticError``, so it escaped all three and one typo in one cell
    aborted the whole file (the wizard 500'd) where the previous ``float()``
    coercion had reported the row and moved on.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{text!r} is not a number") from exc


def _optional_float(raw: Any) -> Optional[float]:
    """``_optional_decimal`` for the preview dataclass, which carries floats."""
    value = _optional_decimal(raw)
    return None if value is None else float(value)


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
                seq1=_optional_float(raw.get("seq1")),
                seq2=_optional_float(raw.get("seq2")),
                exam=_optional_float(raw.get("exam")),
                mock=_optional_float(raw.get("mock")),
                practical=_optional_float(raw.get("practical")),
                remarks=str(raw.get("remarks") or "").strip(),
                raw=raw,
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {idx}: {exc}")
            continue
        rows.append(row)

    return GradeImportPreview(rows=rows, errors=errors)


def _resolve_import_teacher(assignment, teacher_username):
    """Resolve the ``TeacherProfile`` for a grade-import row.

    ``Evaluation.teacher`` is NOT NULL, so every row needs one. Prefer the
    teacher named in the sheet; fall back to whoever actually teaches this
    subject assignment (its first active ``TeacherAssignment``). Returns
    ``None`` ONLY when neither exists — the caller must treat that as a row
    failure and never persist, because a null teacher makes ``save()``'s
    ``full_clean()`` raise ``ValidationError``.

    Both the dry-run and the real apply call this, so the two paths resolve the
    teacher identically and cannot disagree about which rows are importable.
    """
    TeacherProfile = django_apps.get_model("people", "TeacherProfile")
    username = (teacher_username or "").strip()
    if username:
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        teacher = TeacherProfile.objects.filter(user__username=username).first()
        if teacher is not None:
            return teacher
    # No usable teacher on the row — use the subject assignment's own teacher.
    assignment_teacher = (
        assignment.teacher_assignments.filter(is_active=True)
        .select_related("teacher")
        .first()
    )
    return assignment_teacher.teacher if assignment_teacher is not None else None


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
    StudentProfile = django_apps.get_model("people", "StudentProfile")

    created = 0
    updated = 0
    failed = 0
    created_ids = []
    updated_ids = []
    errors: List[dict] = []

    for row_index, row in enumerate(preview.rows, start=1):
        # student_code is unique per school, so pin the lookup to the import's
        # school (via its academic year) — a same-code student at another
        # school must never be matched.
        student = StudentProfile.objects.filter(
            school=academic_year.school, student_code=row.student_code
        ).first()
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
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        term = Term.objects.filter(id=row.term_id).first()

        missing = [
            label
            for label, resolved in (
                ("student", student),
                ("subject_assignment", assignment),
                ("term", term),
            )
            if resolved is None
        ]
        if missing:
            # A row we cannot resolve used to be silently dropped — the dry-run
            # counted it as "would create" and the real run made it vanish.
            failed += 1
            errors.append(
                {
                    "row_index": row_index,
                    "student_code": str(row.student_code or ""),
                    "error": f"could not resolve {', '.join(missing)}",
                }
            )
            continue

        # Evaluation.teacher is NOT NULL. The previous ternary
        # (`teacher or assignment.teacher if hasattr(assignment, "teacher")`)
        # ALWAYS evaluated to None — SubjectAssignment has no `teacher`
        # attribute — so the CSV teacher was thrown away and save()'s
        # full_clean() raised a ValidationError that 500'd the whole import.
        teacher = _resolve_import_teacher(assignment, row.teacher_username)
        if teacher is None:
            failed += 1
            errors.append(
                {
                    "row_index": row_index,
                    "student_code": str(row.student_code or ""),
                    "error": (
                        "no teacher for this subject assignment — add a "
                        "teacher_username column or assign a teacher to the subject"
                    ),
                }
            )
            continue

        try:
            obj, was_created = Evaluation.objects.update_or_create(
                student=student,
                subject_assignment=assignment,
                term=term,
                defaults={
                    "academic_year": academic_year,
                    "teacher": teacher,
                    "seq1_score": row.seq1,
                    "seq2_score": row.seq2,
                    "exam_score": row.exam,
                    "mock_score": row.mock,
                    "practical_score": row.practical,
                    "remarks": row.remarks,
                },
            )
        except _EVALS_IMPORTERS_ROW_ERRORS as exc:
            # One malformed row (bad score, constraint clash) must not abort the
            # whole migration — count it and keep going.
            log_exception_with_context(
                "evals importers apply_import_from_preview row failed",
                school_id=getattr(academic_year, "school_id", None),
                extra={
                    "row_index": row_index,
                    "academic_year_id": getattr(academic_year, "id", None),
                },
            )
            failed += 1
            errors.append(
                {
                    "row_index": row_index,
                    "student_code": str(row.student_code or ""),
                    "error": str(exc)[:200],
                }
            )
            continue

        if was_created:
            created += 1
            created_ids.append(obj.pk)
        else:
            updated += 1
            updated_ids.append(obj.pk)
    return {
        "created": created,
        "updated": updated,
        "failed": failed,
        "errors": errors,
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

            # tenant-isolation-allow: import-pipeline-pk-lookup
            subject_assignment = SubjectAssignment.objects.get(
                id=row.get("subject_assignment_id")
            )
            # student_code is unique per school — pin to the assignment's school.
            student = StudentProfile.objects.get(
                school=subject_assignment.school,
                student_code=row.get("student_code"),
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
                seq1_score=_optional_decimal(row.get("seq1")),
                seq2_score=_optional_decimal(row.get("seq2")),
                exam_score=_optional_decimal(row.get("exam")),
                mock_score=_optional_decimal(row.get("mock")),
                practical_score=_optional_decimal(row.get("practical")),
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
                seq1=_optional_float(row.get("seq1")),
                seq2=_optional_float(row.get("seq2")),
                exam=_optional_float(row.get("exam")),
                mock=_optional_float(row.get("mock")),
                practical=_optional_float(row.get("practical")),
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
    # A dropped row must land in a bucket the caller can see. Logging it and
    # moving on meant 200 lost grades were reported as a clean import.
    failed_count = 0
    errors: list[dict[str, Any]] = []

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
    for row_index, row in enumerate(csv_rows, start=2):
        try:
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            subject_assignment = SubjectAssignment.objects.get(
                id=row.get("subject_assignment_id")
            )
            # student_code is unique per school — pin to the assignment's school.
            student = StudentProfile.objects.get(
                school=subject_assignment.school,
                student_code=row.get("student_code"),
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
                    "seq1_score": _optional_decimal(row.get("seq1")),
                    "seq2_score": _optional_decimal(row.get("seq2")),
                    "exam_score": _optional_decimal(row.get("exam")),
                    "mock_score": _optional_decimal(row.get("mock")),
                    "practical_score": _optional_decimal(row.get("practical")),
                    "remarks": row.get("remarks", ""),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        except _EVALS_IMPORTERS_ROW_ERRORS as exc:
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
            failed_count += 1
            # Enough for a teacher to find the row in their spreadsheet, with
            # no grade values echoed back into the job's error_log.
            errors.append(
                {
                    "row_index": row_index,
                    "student_code": str(row.get("student_code") or ""),
                    "error": str(exc)[:200],
                }
            )
            continue

    duration = time.time() - start_time

    return {
        "created": created_count,
        "updated": updated_count,
        "failed": failed_count,
        "errors": errors,
        "duration_seconds": round(duration, 2),
    }


# How many failed rows are echoed back to the caller / stored on the job.
# Enough to fix a spreadsheet; not so many that one bad upload bloats the row.
IMPORT_ERROR_LOG_CAP = 50


def resolve_import_job_outcome(result: dict) -> tuple[str, int]:
    """Map an ``apply_import`` result to ``(GradeImportJob status, failed row count)``.

    ``GradeImportJob.STATUS_CHOICES`` has carried ``partial`` ("Partially
    Completed") since it was written and nothing ever used it: the apply path
    hard-coded ``"completed"``, so an import that dropped rows reported a clean
    run. Grades are the one dataset a school cannot reconstruct from memory.

    ``.get("failed", 0)`` rather than ``["failed"]`` so an older caller or a
    stubbed importer degrades to the previous shape instead of raising.

    Lives here (not in ``evals.views``) so BOTH the teacher-facing upload view
    and the migration playbook grade step resolve the status identically. The
    view re-exports it under its historical ``_resolve_import_job_outcome`` name.
    """
    failed = int(result.get("failed", 0) or 0)
    if failed:
        return "partial", failed
    return "completed", 0


def apply_grade_import_job(*, academic_year, term, csv_rows, uploaded_by=None):
    """Create a ``GradeImportJob``, apply the rows, and persist the outcome.

    The reusable core of the teacher-facing grade-import view AND the migration
    playbook's grade step (``accounts.migration_services.run_grade_import``), so
    both record an auditable job and dedupe identically (``apply_import`` does
    ``update_or_create`` on ``(academic_year, term, subject_assignment,
    student)``). Row-level failures are counted by ``apply_import`` and never
    raise; a catastrophic apply error marks the job ``failed`` and returns a
    failed result (never raises), so every caller always gets a ``job_id``.

    ``academic_year`` is passed through to ``apply_import`` explicitly — the old
    view called ``apply_import(csv_rows)`` with no year, so evaluations landed
    under ``AcademicYear.filter(is_active=True).first()`` even when the operator
    (and the recorded job) named a different year. Now the grades land under the
    year the job records.
    """
    from django.utils import timezone

    from apps.analytics.models import GradeImportJob

    rows = list(csv_rows)
    author = uploaded_by if getattr(uploaded_by, "is_authenticated", False) else None
    job = GradeImportJob.objects.create(
        academic_year=academic_year,
        term=term,
        uploaded_by=author,
        status="processing",
        created_count=0,
        updated_count=0,
        failed_count=0,
        total_rows=len(rows),
    )

    try:
        result = apply_import(rows, academic_year)
    except _EVALS_IMPORTERS_ROW_ERRORS as exc:
        log_exception_with_context(
            "evals importers apply_grade_import_job apply failed",
            school_id=getattr(academic_year, "school_id", None),
            extra={"academic_year_id": getattr(academic_year, "id", None)},
        )
        job.status = "failed"
        job.failed_count = len(rows) or 1
        job.error_log = [str(exc)[:200]]
        job.completed_at = timezone.now()
        job.save()
        return {
            "created": 0,
            "updated": 0,
            "failed": job.failed_count,
            "errors": [{"error": str(exc)[:200]}],
            "duration_seconds": 0,
            "job_id": job.id,
            "status": "failed",
        }

    status, failed = resolve_import_job_outcome(result)
    job.created_count = result.get("created", 0)
    job.updated_count = result.get("updated", 0)
    job.failed_count = failed
    job.total_rows = len(rows)
    if result.get("errors"):
        job.error_log = result["errors"][:IMPORT_ERROR_LOG_CAP]
    job.status = status
    job.completed_at = timezone.now()
    job.save()

    result["job_id"] = job.id
    result["status"] = status
    result["failed"] = failed
    return result


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
    StudentProfile = django_apps.get_model("people", "StudentProfile")
    AcademicYear = django_apps.get_model("academics", "AcademicYear")

    if not academic_year:
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        academic_year = AcademicYear.objects.filter(is_active=True).first()

    # tenant-isolation-allow: import-pipeline-validates-school-before-persist
    for idx, row in enumerate(csv_rows, start=1):
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        try:
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            subject_assignment = SubjectAssignment.objects.get(
                # tenant-isolation-allow: import-pipeline-validates-school-before-persist
                id=row.get("subject_assignment_id"), academic_year=academic_year
            )
            # student_code is unique per school — pin to the assignment's school.
            student = StudentProfile.objects.get(
                school=subject_assignment.school,
                student_code=row.get("student_code"),
            )
            # tenant-isolation-allow: import-pipeline-validates-school-before-persist
            term = Term.objects.get(id=row.get("term_id"))
            # Resolve the teacher the SAME way the real apply path does, so a
            # row that would fail on apply (no teacher, and Evaluation.teacher is
            # NOT NULL) is flagged here instead of passing the dry-run clean and
            # then 500-ing on apply. The old code discarded this lookup entirely.
            teacher = _resolve_import_teacher(
                subject_assignment, row.get("teacher_username")
            )
            if teacher is None:
                errors.append(
                    f"Row {idx}: no teacher for this subject assignment "
                    "(add a teacher_username column or assign a teacher to the "
                    "subject)"
                )
                continue
            # tenant-isolation-allow: scoped-via-student-and-subject-assignment-resolved-inside-the-validated-import-school
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
