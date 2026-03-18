"""
Enhanced Grade Import Services for:
- Bulk job processing with status tracking
- Delta detection and incremental updates
- Validation and error reporting
- Idempotent operations
- Async processing support
"""

from __future__ import annotations

import io
import csv
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, TYPE_CHECKING
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.utils import IntegrityError, DatabaseError, OperationalError
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.apps import apps as django_apps
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

if TYPE_CHECKING:
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.academics.models import SubjectAssignment

logger = logging.getLogger(__name__)

# Typed exception tuples for §2.4 / §2e row 6 — no broad except
_EVALS_IMPORT_SERVICES_VALIDATE_ROW_ERRORS = (
    KeyError,
    TypeError,
    AttributeError,
    ValueError,
    InvalidOperation,
    LookupError,
)
_EVALS_IMPORT_SERVICES_PROCESS_ROW_ERRORS = (
    ObjectDoesNotExist,
    ValidationError,
    IntegrityError,
    DatabaseError,
    OperationalError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
_EVALS_IMPORT_SERVICES_IMPORT_JOB_ERRORS = (
    ObjectDoesNotExist,
    ValidationError,
    IntegrityError,
    DatabaseError,
    OperationalError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
    IOError,
)


@dataclass
class ImportRowData:
    """Parsed row from import file."""

    student_code: str
    subject_assignment_id: int
    term_id: int
    academic_year_id: int
    teacher_username: Optional[str]
    seq1: Optional[Decimal]
    seq2: Optional[Decimal]
    exam: Optional[Decimal]
    mock: Optional[Decimal]
    practical: Optional[Decimal]
    remarks: str
    raw_row: dict


@dataclass
class ImportRowResult:
    """Result of processing a single row."""

    row_number: int
    row_data: ImportRowData
    action: str  # CREATED, UPDATED, SKIPPED, ERROR
    success: bool
    error_message: str = ""
    previous_values: dict = None
    new_values: dict = None
    student_obj: Optional["StudentProfile"] = None
    subject_assignment_obj: Optional["SubjectAssignment"] = None
    teacher_obj: Optional["TeacherProfile"] = None


class GradeImportValidator:
    """Validates import file structure and content."""

    REQUIRED_HEADERS = [
        "student_code",
        "subject_assignment_id",
        "term_id",
        "academic_year_id",
        "seq1",
        "seq2",
        "exam",
    ]

    OPTIONAL_HEADERS = [
        "teacher_username",
        "mock",
        "practical",
        "remarks",
    ]

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_headers(self, headers: List[str]) -> bool:
        """Check if all required headers present."""
        missing = set(self.REQUIRED_HEADERS) - set(h.lower().strip() for h in headers)
        if missing:
            self.errors.append(f"Missing required headers: {', '.join(missing)}")
            return False
        return True

    def validate_row(
        self, row_num: int, row: dict, academic_year_id: int
    ) -> Tuple[bool, Optional[ImportRowData]]:
        """Validate single row and return parsed data."""
        try:
            # Normalize headers (case-insensitive)
            normalized_row = {k.lower().strip(): v for k, v in row.items()}

            # Parse required fields
            student_code = normalized_row.get("student_code", "").strip()
            if not student_code:
                self.errors.append(f"Row {row_num}: Missing student_code")
                return False, None

            try:
                subject_assignment_id = int(
                    normalized_row.get("subject_assignment_id", 0)
                )
                term_id = int(normalized_row.get("term_id", 0))
            except ValueError:
                self.errors.append(
                    f"Row {row_num}: Invalid subject_assignment_id or term_id (must be integers)"
                )
                return False, None

            # Parse scores (numeric, nullable)
            def parse_score(val):
                if val is None or val == "" or val == "NULL":
                    return None
                try:
                    return Decimal(str(val).strip())
                except (ValueError, TypeError, InvalidOperation):
                    return None

            seq1 = parse_score(normalized_row.get("seq1"))
            seq2 = parse_score(normalized_row.get("seq2"))
            exam = parse_score(normalized_row.get("exam"))
            mock = parse_score(normalized_row.get("mock"))
            practical = parse_score(normalized_row.get("practical"))

            # At least one score required
            if all(s is None for s in [seq1, seq2, exam, mock, practical]):
                self.errors.append(f"Row {row_num}: At least one score required")
                return False, None

            teacher_username = normalized_row.get("teacher_username", "").strip()
            remarks = normalized_row.get("remarks", "").strip()

            row_data = ImportRowData(
                student_code=student_code,
                subject_assignment_id=subject_assignment_id,
                term_id=term_id,
                academic_year_id=academic_year_id,
                teacher_username=teacher_username or None,
                seq1=seq1,
                seq2=seq2,
                exam=exam,
                mock=mock,
                practical=practical,
                remarks=remarks,
                raw_row=row,
            )
            return True, row_data

        except _EVALS_IMPORT_SERVICES_VALIDATE_ROW_ERRORS as e:
            log_exception_with_context(
                "evals import_services: validate_row failed",
                school_id=None,
                extra={"row_num": row_num, "error": str(e)},
            )
            self.errors.append(f"Row {row_num}: {str(e)}")
            return False, None

    def is_valid(self) -> bool:
        return len(self.errors) == 0


class GradeImportProcessor:
    """
    Processes validated import data:
    - Resolves student/teacher/assignment records
    - Detects changes (delta)
    - Updates or creates evaluations
    - Logs all operations
    """

    def __init__(self, academic_year):
        self.academic_year = academic_year
        self.StudentProfile = django_apps.get_model("people", "StudentProfile")
        self.TeacherProfile = django_apps.get_model("people", "TeacherProfile")
        self.SubjectAssignment = django_apps.get_model("academics", "SubjectAssignment")
        self.Term = django_apps.get_model("academics", "Term")
        self.Evaluation = django_apps.get_model("evals", "Evaluation")
        self.AssessmentWeights = django_apps.get_model("evals", "AssessmentWeights")

    def process_rows(
        self,
        rows: List[ImportRowData],
        dry_run: bool = False,
    ) -> List[ImportRowResult]:
        """
        Process list of rows. Returns results with before/after values.
        """
        results = []

        for idx, row_data in enumerate(rows, start=1):
            result = self._process_single_row(row_data, idx, dry_run)
            results.append(result)

        return results

    def _process_single_row(
        self, row_data: ImportRowData, row_number: int, dry_run: bool
    ) -> ImportRowResult:
        """Process single row and return result."""
        try:
            # Resolve database objects
            student = self.StudentProfile.objects.filter(
                student_code=row_data.student_code
            ).first()
            if not student:
                return ImportRowResult(
                    row_number=row_number,
                    row_data=row_data,
                    action="ERROR",
                    success=False,
                    error_message=f"Student not found: {row_data.student_code}",
                )

            subject_assignment = self.SubjectAssignment.objects.filter(
                id=row_data.subject_assignment_id, academic_year=self.academic_year
            ).first()
            if not subject_assignment:
                return ImportRowResult(
                    row_number=row_number,
                    row_data=row_data,
                    action="ERROR",
                    success=False,
                    error_message=f"Subject assignment not found: {row_data.subject_assignment_id}",
                )

            term = self.Term.objects.filter(id=row_data.term_id).first()
            if not term:
                return ImportRowResult(
                    row_number=row_number,
                    row_data=row_data,
                    action="ERROR",
                    success=False,
                    error_message=f"Term not found: {row_data.term_id}",
                )

            teacher = None
            if row_data.teacher_username:
                teacher = self.TeacherProfile.objects.filter(
                    user__username=row_data.teacher_username
                ).first()

            # Build new values
            new_values = {
                "seq1_score": row_data.seq1,
                "seq2_score": row_data.seq2,
                "exam_score": row_data.exam,
                "mock_score": row_data.mock,
                "practical_score": row_data.practical,
                "remarks": row_data.remarks,
            }

            # Try to get existing evaluation
            existing_eval = self.Evaluation.objects.filter(
                student=student,
                subject_assignment=subject_assignment,
                term=term,
                academic_year=self.academic_year,
            ).first()

            # Capture previous state
            previous_values = {}
            if existing_eval:
                previous_values = {
                    "seq1_score": existing_eval.seq1_score,
                    "seq2_score": existing_eval.seq2_score,
                    "exam_score": existing_eval.exam_score,
                    "mock_score": existing_eval.mock_score,
                    "practical_score": existing_eval.practical_score,
                    "remarks": existing_eval.remarks,
                }

            # Detect if anything changed
            has_changes = False
            if existing_eval:
                has_changes = any(
                    previous_values.get(k) != v for k, v in new_values.items()
                )

            # Perform update/create
            action = "SKIPPED"
            if not existing_eval:
                if not dry_run:
                    self.Evaluation.objects.create(
                        academic_year=self.academic_year,
                        student=student,
                        subject_assignment=subject_assignment,
                        term=term,
                        teacher=teacher,
                        **new_values,
                    )
                action = "CREATED"
            elif has_changes:
                if not dry_run:
                    for k, v in new_values.items():
                        setattr(existing_eval, k, v)
                    if teacher:
                        existing_eval.teacher = teacher
                    existing_eval.save()
                action = "UPDATED"

            # Convert Decimals to float for JSON
            previous_values_json = {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in previous_values.items()
            }
            new_values_json = {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in new_values.items()
            }

            return ImportRowResult(
                row_number=row_number,
                row_data=row_data,
                action=action,
                success=True,
                previous_values=previous_values_json,
                new_values=new_values_json,
                student_obj=student,
                subject_assignment_obj=subject_assignment,
                teacher_obj=teacher,
            )

        except _EVALS_IMPORT_SERVICES_PROCESS_ROW_ERRORS as e:
            school_id = getattr(self.academic_year, "school_id", None)
            log_exception_with_context(
                "evals import_services: process row failed",
                school_id=school_id,
                extra={
                    "row_number": row_number,
                    "student_code": row_data.student_code,
                    "error": str(e),
                },
            )
            return ImportRowResult(
                row_number=row_number,
                row_data=row_data,
                action="ERROR",
                success=False,
                error_message=str(e),
            )


class GradeImportService:
    """
    High-level service orchestrating import workflow:
    1. Read file
    2. Validate
    3. Process rows
    4. Create job record
    5. Log results
    """

    def __init__(self):
        self.GradeImportJob = django_apps.get_model("evals", "GradeImportJob")
        self.GradeImportRowLog = django_apps.get_model("evals", "GradeImportRowLog")

    def compute_file_hash(self, file_obj: UploadedFile) -> str:
        """Compute SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        for chunk in file_obj.chunks():
            sha256.update(chunk)
        return sha256.hexdigest()

    def read_csv_file(self, file_obj: UploadedFile) -> Tuple[List[str], List[dict]]:
        """Read CSV file and return headers + rows."""
        file_obj.seek(0)
        text_file = io.TextIOWrapper(file_obj, encoding="utf-8")
        reader = csv.DictReader(text_file)

        if not reader.fieldnames:
            raise ValueError("CSV file appears to be empty")

        rows = list(reader)
        return list(reader.fieldnames), rows

    @transaction.atomic
    def import_grades(
        self,
        file_obj: UploadedFile,
        academic_year,
        term,
        uploaded_by,
        dry_run: bool = False,
    ) -> "GradeImportJob":
        """
        Complete import workflow:
        1. Create job record
        2. Validate file
        3. Process rows
        4. Log results
        """

        file_hash = self.compute_file_hash(file_obj)
        filename = file_obj.name
        file_size = file_obj.size
        file_obj.seek(0)

        # Check for duplicate uploads
        duplicate = self.GradeImportJob.objects.filter(file_hash=file_hash).first()
        if duplicate and duplicate.status == self.GradeImportJob.Status.COMPLETED:
            logger.warning(f"Duplicate file detected: {filename}")

        # Create job record
        job = self.GradeImportJob.objects.create(
            academic_year=academic_year,
            term=term,
            uploaded_by=uploaded_by,
            filename=filename,
            file_size_bytes=file_size,
            file_hash=file_hash,
            uploaded_file=file_obj,
            status=self.GradeImportJob.Status.VALIDATING,
        )

        try:
            # Read and parse file
            headers, rows = self.read_csv_file(file_obj)
            job.total_rows = len(rows)

            # Validate
            validator = GradeImportValidator()
            if not validator.validate_headers(headers):
                job.status = self.GradeImportJob.Status.FAILED
                job.error_summary = json.dumps({"header_errors": validator.errors})
                job.save()
                return job

            # Parse rows
            parsed_rows = []
            for idx, raw_row in enumerate(rows, start=1):
                is_valid, row_data = validator.validate_row(
                    idx, raw_row, academic_year.id
                )
                if is_valid:
                    parsed_rows.append(row_data)

            job.valid_rows = len(parsed_rows)

            if validator.errors:
                job.status = self.GradeImportJob.Status.PARTIAL
                job.error_summary = json.dumps(
                    {
                        "validation_errors": validator.errors[:100]  # Limit to 100
                    }
                )
            else:
                job.status = self.GradeImportJob.Status.PROCESSING

            job.save()

            if not parsed_rows:
                job.status = self.GradeImportJob.Status.FAILED
                job.save()
                return job

            # Process rows
            job.started_processing_at = timezone.now()
            job.save()

            processor = GradeImportProcessor(academic_year)
            results = processor.process_rows(parsed_rows, dry_run=dry_run)

            # Log results and update job stats
            if not dry_run:
                for result in results:
                    self.GradeImportRowLog.objects.create(
                        import_job=job,
                        row_number=result.row_number,
                        student=result.student_obj,
                        subject_assignment=result.subject_assignment_obj,
                        teacher=result.teacher_obj,
                        action=result.action,
                        success=result.success,
                        error_message=result.error_message,
                        previous_values=result.previous_values or {},
                        new_values=result.new_values or {},
                    )

            # Update job stats
            job.rows_created = sum(1 for r in results if r.action == "CREATED")
            job.rows_updated = sum(1 for r in results if r.action == "UPDATED")
            job.rows_error = sum(1 for r in results if r.action == "ERROR")

            job.completed_at = timezone.now()
            if job.rows_error > 0:
                job.status = self.GradeImportJob.Status.PARTIAL
            else:
                job.status = self.GradeImportJob.Status.COMPLETED

            job.processing_notes = f"Processed {job.total_rows} rows: {job.rows_created} created, {job.rows_updated} updated, {job.rows_error} errors"
            job.save()

            return job

        except _EVALS_IMPORT_SERVICES_IMPORT_JOB_ERRORS as e:
            school_id = getattr(academic_year, "school_id", None)
            log_exception_with_context(
                "evals import_services: import_grades failed",
                school_id=school_id,
                extra={
                    "job_id": job.id,
                    "academic_year_id": academic_year.id,
                    "error": str(e),
                },
            )
            job.status = self.GradeImportJob.Status.FAILED
            job.error_summary = json.dumps({"fatal_error": str(e)})
            job.completed_at = timezone.now()
            job.save()
            return job
