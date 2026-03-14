"""
Enhanced Evaluation Models for:
- Bulk grade import job tracking
- Delta detection (incremental updates)
- Offline sync support
- Import audit logs
- Technical assessments (practical/portfolio)
- Cameroon-specific dual-system (Anglophone/Francophone)
"""

from django.db import models
from decimal import Decimal
import json

from apps.academics.models import AcademicYear, Term, SubjectAssignment
from apps.people.models import TeacherProfile, StudentProfile
from apps.accounts.validators import (
    validate_grade_import_file,
    validate_file_size_5mb,
    validate_evidence_file,
    validate_file_size_20mb,
)
from apps.accounts.models import User


class GradeImportJob(models.Model):
    """
    Tracks a single grade import session/upload.
    Supports: CSV/XLSX upload, preview, validation, batch processing, and status tracking.
    """
    
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VALIDATING = "VALIDATING", "Validating"
        PREVIEW = "PREVIEW", "Preview Ready"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        PARTIAL = "PARTIAL", "Partially Completed"
    
    # Upload metadata
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="grade_import_jobs")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="grade_import_jobs")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="grade_imports_uploaded")
    uploaded_file = models.FileField(
        upload_to="grade_imports/%Y/%m/%d/",
        validators=[validate_grade_import_file, validate_file_size_5mb],
    )
    file_hash = models.CharField(max_length=64, unique=True)  # SHA256 for duplicate detection
    
    # Status & timing
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_processing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_error = models.PositiveIntegerField(default=0)
    
    # Details
    filename = models.CharField(max_length=255)
    file_size_bytes = models.PositiveIntegerField()
    error_summary = models.TextField(blank=True, help_text="JSON summary of validation/processing errors")
    processing_notes = models.TextField(blank=True)
    
    # Optional: delta detection
    is_delta_update = models.BooleanField(default=False, help_text="True if this is incremental update")
    previous_import = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subsequent_imports",
        help_text="Previous import in chain for delta tracking"
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Grade Import Job"
        indexes = [
            models.Index(fields=["academic_year", "term", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.status}) - {self.academic_year} {self.term.label}"
    
    @property
    def duration_seconds(self) -> int | None:
        if self.completed_at and self.started_processing_at:
            delta = self.completed_at - self.started_processing_at
            return int(delta.total_seconds())
        return None
    
    @property
    def success_rate(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round((self.valid_rows / self.total_rows) * 100, 2)
    
    def get_error_summary(self) -> dict:
        """Parse JSON error summary."""
        if not self.error_summary:
            return {}
        try:
            return json.loads(self.error_summary)
        except (TypeError, ValueError):
            return {}


class GradeImportRowLog(models.Model):
    """
    Audit log for each row processed in an import job.
    Tracks what happened to each student-subject-term record.
    """
    
    class Action(models.TextChoices):
        CREATED = "CREATED", "Record Created"
        UPDATED = "UPDATED", "Record Updated"
        SKIPPED = "SKIPPED", "Skipped (No Change)"
        ERROR = "ERROR", "Error"
        DELTA_DETECTED = "DELTA_DETECTED", "Delta Detected (Pending Review)"
    
    # Link to parent job
    import_job = models.ForeignKey(GradeImportJob, on_delete=models.CASCADE, related_name="row_logs")
    
    # Row identity
    row_number = models.PositiveIntegerField()
    student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, related_name="import_row_logs")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.SET_NULL, null=True)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Action & result
    action = models.CharField(max_length=20, choices=Action.choices)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    # Data before/after
    previous_values = models.JSONField(default=dict, help_text="Old Evaluation scores before update")
    new_values = models.JSONField(default=dict, help_text="New Evaluation scores after update")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["import_job", "row_number"]
        verbose_name = "Grade Import Row Log"
        indexes = [
            models.Index(fields=["import_job", "row_number"]),
            models.Index(fields=["action"]),
            models.Index(fields=["student", "-created_at"]),
        ]
    
    def __str__(self):
        return f"Row {self.row_number}: {self.student} - {self.action}"
    
    @property
    def has_changes(self) -> bool:
        """True if this update actually changed data."""
        return bool(self.previous_values != self.new_values)


class EvaluationDelta(models.Model):
    """
    Detects and tracks differences between consecutive uploads for the same
    student-subject-term combination.
    
    Enables idempotent processing: only apply changes if data differs.
    """
    
    class ChangeType(models.TextChoices):
        NEW = "NEW", "New Record"
        SCORE_CHANGE = "SCORE_CHANGE", "Score Changed"
        REMARKS_CHANGE = "REMARKS_CHANGE", "Remarks Changed"
        TEACHER_CHANGE = "TEACHER_CHANGE", "Teacher Changed"
        DUPLICATE = "DUPLICATE", "Duplicate Upload"
    
    # Parent imports
    from_import = models.ForeignKey(GradeImportJob, on_delete=models.CASCADE, related_name="deltas_detected")
    to_import = models.ForeignKey(
        GradeImportJob,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="deltas_applied"
    )
    
    # Data identity
    evaluation = models.ForeignKey(
        "evals.Evaluation",
        on_delete=models.CASCADE,
        related_name="deltas"
    )
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="evaluation_deltas")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    
    # Change description
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    previous_state = models.JSONField(default=dict)
    new_state = models.JSONField(default=dict)
    
    # Approval workflow (optional)
    requires_review = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_deltas"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved = models.BooleanField(null=True, blank=True)
    
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "Evaluation Delta"
        unique_together = ("from_import", "evaluation")
    
    def __str__(self):
        return f"{self.student} - {self.change_type} ({self.from_import.id})"


class OfflineGradeQueue(models.Model):
    """
    Queues grade changes made offline (no internet).
    Syncs to server when connection restored.
    """
    
    class SyncStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Sync"
        SYNCING = "SYNCING", "Syncing"
        SYNCED = "SYNCED", "Synced"
        CONFLICT = "CONFLICT", "Conflict"
    
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    
    # What was changed
    seq1_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    seq2_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mock_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    practical_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)
    
    # Sync metadata
    status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    device_id = models.CharField(max_length=255, help_text="Device that made the change")
    offline_timestamp = models.DateTimeField(help_text="When change was made offline")
    
    class Meta:
        unique_together = ("student", "subject_assignment", "term")
        ordering = ["status", "created_at"]
    
    def __str__(self):
        return f"{self.student} - {self.status}"


class EvaluationEvidence(models.Model):
    """
    Attachments for evaluations: photos, videos, documents for practical/technical assessments.
    Supports portfolio-based grading.
    """
    
    class EvidenceType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document"
        RUBRIC = "RUBRIC", "Rubric Submission"
    
    evaluation = models.ForeignKey(
        "evals.Evaluation",
        on_delete=models.CASCADE,
        related_name="evidence"
    )
    evidence_type = models.CharField(max_length=20, choices=EvidenceType.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # File storage
    file = models.FileField(
        upload_to="evaluations/evidence/%Y/%m/%d/",
        validators=[validate_evidence_file, validate_file_size_20mb],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Optional: metadata
    file_size_bytes = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100)
    
    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name_plural = "Evaluation Evidence"
    
    def __str__(self):
        return f"{self.evaluation.student} - {self.get_evidence_type_display()}"


class CompetencyRubric(models.Model):
    """
    Digital rubric for technical/practical skills assessment.
    Teachers check off competencies observed during practical sessions.
    """
    
    class CompetencyLevel(models.TextChoices):
        NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT", "Needs Improvement"
        DEVELOPING = "DEVELOPING", "Developing"
        PROFICIENT = "PROFICIENT", "Proficient"
        ADVANCED = "ADVANCED", "Advanced"
    
    # Rubric metadata
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="competency_rubrics")
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE)
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["subject_assignment", "name"]
        verbose_name = "Competency Rubric"
    
    def __str__(self):
        return f"{self.subject_assignment.subject.name} - {self.name}"


class CompetencyItem(models.Model):
    """Individual skill/competency within a rubric."""
    
    rubric = models.ForeignKey(CompetencyRubric, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255, help_text="e.g., 'Circuit Wiring', 'Welding Technique'")
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ["rubric", "order"]
    
    def __str__(self):
        return f"{self.rubric.name} > {self.name}"


class StudentCompetencyAssessment(models.Model):
    """
    Assessment of a student's competency on a specific item.
    Multiple assessments per student per competency item = portfolio over time.
    """
    
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="competency_assessments")
    competency_item = models.ForeignKey(CompetencyItem, on_delete=models.CASCADE, related_name="student_assessments")
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE)
    
    # Assessment result
    level = models.CharField(max_length=20, choices=CompetencyItem.CompetencyLevel.choices)
    observations = models.TextField(blank=True, help_text="Teacher notes on this competency")
    
    # Linked evidence
    evidence = models.ForeignKey(
        EvaluationEvidence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="competency_assessments"
    )
    
    assessed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-assessed_at"]
        verbose_name = "Student Competency Assessment"
    
    def __str__(self):
        return f"{self.student} - {self.competency_item.name} ({self.level})"


class ClockHourTracking(models.Model):
    """
    Tracks mandatory workshop/practical hours for technical certifications.
    E.g., Intermediate Technical Certificate (ITC) requires X hours.
    """
    
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="clock_hour_records")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE)
    
    date = models.DateField()
    hours = models.DecimalField(max_digits=4, decimal_places=2, help_text="Hours spent in workshop")
    activity_description = models.CharField(max_length=255, help_text="e.g., 'Welding - Arc Techniques'")
    
    recorded_by = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-date"]
        verbose_name = "Clock Hour Record"
        unique_together = ("student", "subject_assignment", "date")
    
    def __str__(self):
        return f"{self.student} - {self.hours}h - {self.date}"
    
    @classmethod
    def total_hours_for_student(cls, student, subject_assignment, start_date=None, end_date=None):
        """Calculate total hours for a student in a subject."""
        qs = cls.objects.filter(student=student, subject_assignment=subject_assignment)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        total = qs.aggregate(models.Sum("hours"))["hours__sum"] or Decimal("0")
        return total


class ReportCardTemplate(models.Model):
    """
    Customizable report card templates with Cameroon dual-system support.
    Supports: English (Anglophone), French (Francophone), and Technical education.
    """
    
    class EducationSystem(models.TextChoices):
        ANGLOPHONE = "ANGLOPHONE", "Anglophone (English)"
        FRANCOPHONE = "FRANCOPHONE", "Francophone (French)"
        TECHNICAL = "TECHNICAL", "Technical/Professional"
    
    class ReportType(models.TextChoices):
        TERM = "TERM", "Term Report"
        ANNUAL = "ANNUAL", "Annual Report"
        MOCK = "MOCK", "Mock Exam Report"
    
    # Metadata
    name = models.CharField(max_length=255)
    education_system = models.CharField(max_length=20, choices=EducationSystem.choices)
    report_type = models.CharField(max_length=20, choices=ReportType.choices)
    is_active = models.BooleanField(default=True)
    
    # Customization
    school_logo = models.ImageField(upload_to="report_templates/logos/", null=True, blank=True)
    school_letterhead_text = models.TextField(blank=True, help_text="School name, address, contact info")
    
    # Colors & styling
    primary_color = models.CharField(max_length=7, default="#0d6efd")  # Hex color
    secondary_color = models.CharField(max_length=7, default="#198754")
    accent_color = models.CharField(max_length=7, default="#dc3545")
    background_color = models.CharField(max_length=7, default="#ffffff")
    text_color = models.CharField(max_length=7, default="#000000")
    
    # Signature fields
    include_principal_signature = models.BooleanField(default=True)
    include_class_teacher_signature = models.BooleanField(default=True)
    include_parent_acknowledgement = models.BooleanField(default=True)
    
    # Content sections
    include_conduct_grade = models.BooleanField(default=True)
    include_class_rank = models.BooleanField(default=True)
    include_school_rank = models.BooleanField(default=True)
    include_promotion_status = models.BooleanField(default=True)
    include_teacher_comments = models.BooleanField(default=True)
    include_attendance = models.BooleanField(default=True)
    
    # Grading scale (for Cameroon compatibility)
    # Anglophone: A-E (GCE)
    # Francophone: /20 scale
    grading_scale_type = models.CharField(
        max_length=20,
        choices=[
            ("A_E", "A-E Scale (GCE)"),
            ("NUMERIC_20", "/20 Scale (Francophone)"),
            ("NUMERIC_100", "/100 Scale"),
        ],
        default="A_E"
    )
    
    # HTML template content
    html_template = models.TextField(
        help_text="HTML template with template variables like {{student_name}}, {{total_score}}, etc."
    )
    css_styles = models.TextField(blank=True, help_text="Additional CSS styling")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ["education_system", "report_type", "name"]
        verbose_name = "Report Card Template"
    
    def __str__(self):
        return f"{self.get_education_system_display()} - {self.get_report_type_display()} - {self.name}"


class ReportCardCustomization(models.Model):
    """
    Per-classroom customization of report card appearance/content.
    Allows schools to use different templates for different classes.
    """
    
    classroom = models.OneToOneField(
        "academics.Classroom",
        on_delete=models.CASCADE,
        related_name="report_card_customization"
    )
    template = models.ForeignKey(ReportCardTemplate, on_delete=models.PROTECT)
    
    # Classroom-specific overrides
    override_header_text = models.TextField(blank=True)
    override_footer_text = models.TextField(blank=True)
    custom_css = models.TextField(blank=True)
    
    # Show/hide sections per classroom
    show_conduct_grade = models.BooleanField(default=True)
    show_class_rank = models.BooleanField(default=True)
    show_school_rank = models.BooleanField(default=True)
    show_mock_scores = models.BooleanField(default=False)  # For Form 5/7
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Report Card Customization"
    
    def __str__(self):
        return f"{self.classroom.name} - {self.template.name}"


class MockExamSession(models.Model):
    """
    Tracks mock exam sessions for Form 5/7 students preparing for GCE.
    Separate from regular term evaluations.
    """
    
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, help_text="e.g., 'Mock 1', 'Final Mock'")
    
    exam_date = models.DateField()
    results_published_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["exam_date"]
        verbose_name = "Mock Exam Session"
        unique_together = ("academic_year", "term", "name")
    
    def __str__(self):
        return f"{self.name} - {self.exam_date}"


class MockExamEvaluation(models.Model):
    """
    Student's mock exam scores (linked to MockExamSession, not regular Evaluation).
    """
    
    mock_session = models.ForeignKey(MockExamSession, on_delete=models.CASCADE, related_name="evaluations")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE)
    
    score = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=2, blank=True, help_text="e.g., A, B, C, D, E")
    remarks = models.TextField(blank=True)
    
    recorded_by = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["mock_session", "student", "subject_assignment"]
        unique_together = ("mock_session", "student", "subject_assignment")
        verbose_name = "Mock Exam Evaluation"
    
    def __str__(self):
        return f"{self.student} - {self.mock_session.name} - {self.subject_assignment.subject.name}"
