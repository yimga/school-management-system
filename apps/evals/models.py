from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.academics.models import AcademicYear, Term, SubjectAssignment
from apps.people.models import TeacherProfile, StudentProfile
from apps.accounts.models import User


class AssessmentWeights(models.Model):
    """Weighting configuration for evaluation components.

    Cameroon schools commonly use continuous assessment + exams.
    Technical schools may also include Practical/TP and Mock exams.

    This model lets you define weights at two levels:
    - school-wide for an academic year (classroom = NULL)
    - per-classroom override (classroom = ...)

    We keep it in the evals app because it drives score computation.
    """

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="assessment_weights")
    term = models.ForeignKey(
        Term,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_weights",
        help_text="Optional term-specific override. Leave blank for full-year defaults.",
    )
    # Optional per-classroom override. We avoid importing Classroom directly to prevent circular imports.
    classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_weights",
    )

    # Percent weights (0..100). Defaults are a common pattern: 20/20/60.
    seq1_weight = models.PositiveSmallIntegerField(default=20)
    seq2_weight = models.PositiveSmallIntegerField(default=20)
    exam_weight = models.PositiveSmallIntegerField(default=60)
    mock_weight = models.PositiveSmallIntegerField(default=0)
    practical_weight = models.PositiveSmallIntegerField(default=0)

    # Score scale is usually /20 in Cameroon, but we keep this flexible.
    score_scale = models.PositiveSmallIntegerField(default=20)
    
    # NEW: Grading scale & locale configuration
    grading_scale = models.CharField(
        max_length=50,
        choices=[
            ('numeric_0_20', 'Numeric 0–20 (Cameroon Francophone)'),
            ('letter_a_e', 'Letters A–E (Cameroon Anglophone)'),
            ('gpa_4_0', 'GPA 4.0 Scale'),
            ('percentage', 'Percentage 0–100'),
        ],
        default='numeric_0_20'
    )
    region = models.CharField(
        max_length=50,
        choices=[
            ('cameroon_anglophone', 'Cameroon Anglophone'),
            ('cameroon_francophone', 'Cameroon Francophone'),
            ('global', 'Global/Other'),
        ],
        default='cameroon_anglophone'
    )
    
    # Letter grade mapping thresholds (for A–E scales)
    grade_a_min = models.DecimalField(max_digits=5, decimal_places=2, default=18.00, help_text="Minimum score for A")
    grade_b_min = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)
    grade_c_min = models.DecimalField(max_digits=5, decimal_places=2, default=14.00)
    grade_d_min = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    grade_e_min = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ("academic_year", "term", "classroom")

    def clean(self):
        if AssessmentWeights.objects.filter(
            academic_year=self.academic_year,
            term=self.term,
            classroom=self.classroom,
        ).exclude(pk=self.pk).exists():
            raise ValidationError("Assessment weights already exist for this year/term/classroom.")
        total = (
            self.seq1_weight
            + self.seq2_weight
            + self.exam_weight
            + self.mock_weight
            + self.practical_weight
        )
        if total <= 0:
            raise ValidationError("At least one component weight must be > 0.")
        if total > 100:
            raise ValidationError("Total weights cannot exceed 100%.")
        if self.score_scale <= 0:
            raise ValidationError("Score scale must be > 0.")

    @classmethod
    def get_for(cls, academic_year: AcademicYear, classroom=None, term: Term | None = None) -> "AssessmentWeights":
        """Return the best matching weights.

        Precedence:
        1) classroom override for term (if provided)
        2) school-wide term default
        3) classroom override for full year
        4) school-wide default
        If none exists, create a school-wide default.
        """
        if term is not None:
            if classroom is not None:
                obj = cls.objects.filter(
                    academic_year=academic_year,
                    term=term,
                    classroom=classroom,
                ).first()
                if obj:
                    return obj
            obj = cls.objects.filter(
                academic_year=academic_year,
                term=term,
                classroom__isnull=True,
            ).first()
            if obj:
                return obj

        if classroom is not None:
            obj = cls.objects.filter(
                academic_year=academic_year,
                term__isnull=True,
                classroom=classroom,
            ).first()
            if obj:
                return obj

        obj = cls.objects.filter(
            academic_year=academic_year,
            term__isnull=True,
            classroom__isnull=True,
        ).first()
        if obj:
            return obj

        # Create a sensible default
        return cls.objects.create(
            academic_year=academic_year,
            term=None,
            classroom=None,
            seq1_weight=20,
            seq2_weight=20,
            exam_weight=60,
            mock_weight=0,
            practical_weight=0,
            score_scale=20,
        )

    def __str__(self) -> str:
        scope = f"{self.classroom}" if self.classroom_id else "School default"
        term_label = self.term.label if self.term_id else "All terms"
        return f"Weights ({scope}) {self.academic_year} • {term_label}"


class TeacherAssignment(models.Model):
    """
    Teacher is allowed to enter marks for a given SubjectAssignment in an AcademicYear.
    """
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="assignments")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="teacher_assignments")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.CASCADE, related_name="teacher_assignments")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("teacher", "academic_year", "subject_assignment")

    def clean(self):
        # Enforce year consistency between assignment and subject_assignment
        if self.subject_assignment and self.academic_year and self.subject_assignment.academic_year_id != self.academic_year_id:
            raise ValidationError("SubjectAssignment academic year must match TeacherAssignment academic year.")

    def __str__(self):
        return f"{self.teacher} -> {self.subject_assignment}"


class Evaluation(models.Model):
    """
    One row per student per subject_assignment per term.
    Phase 4: Critical model for audit logging (grade changes).
    """
    # Phase 4: Enable audit logging for this critical model
    audit_enabled = True

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="evaluations")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="evaluations")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.PROTECT, related_name="evaluations")
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="evaluations")
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name="evaluations")

    # Backward compatible fields (old UI). New UI should use seq1/seq2.
    test1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    test2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Expanded components (Cameroon English sub-system + technical schools)
    # Validators: 0-20 scale for Cameroon. Override if using different scale.
    seq1_score = models.DecimalField(
        "Seq 1",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    seq2_score = models.DecimalField(
        "Seq 2",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    exam_score = models.DecimalField(
        "Exam",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    mock_score = models.DecimalField(
        "Mock",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    practical_score = models.DecimalField(
        "Practical",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    remarks = models.CharField(max_length=255, blank=True)
    
    # NEW: Grade conversion & practical assessment
    letter_grade = models.CharField(max_length=1, choices=[
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'),
        ('', 'Not Graded')
    ], blank=True, default='')
    clock_hours = models.PositiveIntegerField(default=0)
    practical_status = models.CharField(max_length=20, choices=[
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], default='not_started')
    assessment_date = models.DateField(null=True, blank=True)
    validation_flags = models.JSONField(default=dict, blank=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Audit logging fields for data integrity
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluations_created',
        help_text="User who created this evaluation"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluations_updated',
        help_text="User who last updated this evaluation"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - preserves evaluation history"
    )


    @property
    def total_score(self) -> float:
        """Single score used for ranking/statistics.

        Uses configurable weights from AssessmentWeights.
        Falls back to a sensible default if no config exists.
        """
        # Prefer new fields; fall back to legacy if new fields are empty.
        s1 = self.seq1_score if self.seq1_score is not None else self.test1
        s2 = self.seq2_score if self.seq2_score is not None else self.test2

        # Weights are configured per school (and optionally per classroom).
        # Terms do not affect weights.
        weights = AssessmentWeights.get_for(
            academic_year=self.academic_year,
            classroom=self.subject_assignment.classroom if self.subject_assignment_id else None,
            term=self.term,
        )
        components = {
            "seq1": (s1, weights.seq1_weight),
            "seq2": (s2, weights.seq2_weight),
            "exam": (self.exam_score, weights.exam_weight),
            "mock": (self.mock_score, weights.mock_weight),
            "practical": (self.practical_score, weights.practical_weight),
        }

        total_w = 0
        total = 0.0
        for _, (val, w) in components.items():
            if w <= 0:
                continue
            total_w += w
            score_val = float(val) if val is not None else 0.0
            total += score_val * w

        if total_w <= 0:
            return 0.0
        return round(total / total_w, 2)

    @property
    def is_complete_for_ranking(self) -> bool:
        """True when all required (weighted) components have scores."""
        weights = AssessmentWeights.get_for(
            academic_year=self.academic_year,
            classroom=self.subject_assignment.classroom if self.subject_assignment_id else None,
            term=self.term,
        )
        s1 = self.seq1_score if self.seq1_score is not None else self.test1
        s2 = self.seq2_score if self.seq2_score is not None else self.test2
        req = []
        if weights.seq1_weight > 0:
            req.append(s1)
        if weights.seq2_weight > 0:
            req.append(s2)
        if weights.exam_weight > 0:
            req.append(self.exam_score)
        if weights.mock_weight > 0:
            req.append(self.mock_score)
        if weights.practical_weight > 0:
            req.append(self.practical_score)
        return all(v is not None for v in req)

    class Meta:
        unique_together = ("academic_year", "term", "subject_assignment", "student")

    def clean(self):
        # Validate score ranges (0-20 for Cameroon)
        score_fields = {
            'seq1_score': self.seq1_score,
            'seq2_score': self.seq2_score,
            'exam_score': self.exam_score,
            'mock_score': self.mock_score,
            'practical_score': self.practical_score,
        }
        
        for field_name, score in score_fields.items():
            if score is not None:
                if score < 0:
                    raise ValidationError({field_name: f"{field_name} cannot be negative"})
                if score > 20:
                    raise ValidationError({field_name: f"{field_name} cannot exceed 20"})
        
        # At least one score must be entered
        scores = [s for s in score_fields.values() if s is not None]
        if not scores and not self.test1 and not self.test2:
            raise ValidationError("At least one score must be entered")
        
        # enforce year/term match
        if self.term and self.academic_year and self.term.academic_year_id != self.academic_year_id:
            raise ValidationError("Term academic year must match Evaluation academic year.")
        # enforce subject assignment matches year/term
        if self.subject_assignment and self.academic_year and self.subject_assignment.academic_year_id != self.academic_year_id:
            raise ValidationError("SubjectAssignment year must match Evaluation year.")
        if self.subject_assignment and self.term and self.subject_assignment.term_id != self.term_id:
            raise ValidationError("SubjectAssignment term must match Evaluation term.")
        # enforce student in same year/class/specialty as subject assignment
        if self.subject_assignment and self.student:
            sa = self.subject_assignment
            if self.student.academic_year_id != sa.academic_year_id:
                raise ValidationError("Student year must match SubjectAssignment year.")
            if self.student.classroom_id != sa.classroom_id or self.student.specialty_id != sa.specialty_id:
                raise ValidationError("Student class/specialty must match SubjectAssignment class/specialty.")

    def save(self, *args, **kwargs):
        """Call full_clean() before saving to validate scores."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} | {self.subject_assignment.subject} | {self.term}"


class EvaluationEvidence(models.Model):
    class MediaType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="evidence")
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.PHOTO)
    file = models.FileField(upload_to="evaluations/evidence/")
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.evaluation} - {self.get_media_type_display()}"

# ========== GRADE AUDIT TRAIL ==========

class GradeAudit(models.Model):
    """Immutable audit trail for all grade changes.
    Phase 4: Enable audit logging to track audit record creation.
    """
    # Phase 4: Enable audit logging for this model
    audit_enabled = True

    CHANGE_TYPE_CHOICES = [
        ('create', 'Grade Created'),
        ('update', 'Grade Updated'),
        ('delete', 'Grade Deleted'),
        ('rollback', 'Grade Rolled Back'),
        ('import', 'Imported from CSV'),
        ('offline_sync', 'Synced Offline Entry'),
    ]
    
    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.PROTECT,
        related_name='audit_trail'
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES)
    
    # Before/after snapshots
    seq1_before = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    seq1_after = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    seq2_before = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    seq2_after = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exam_before = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exam_after = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mock_before = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mock_after = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    practical_before = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    practical_after = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks_before = models.TextField(null=True, blank=True)
    remarks_after = models.TextField(null=True, blank=True)
    
    # Validation & conflict
    validation_errors = models.JSONField(default=list, blank=True)
    offline_conflict_resolved = models.BooleanField(default=False)
    conflict_resolution_note = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['evaluation', '-changed_at']),
            models.Index(fields=['changed_by', '-changed_at']),
            models.Index(fields=['change_type', '-changed_at']),
        ]
    
    def __str__(self):
        return f"{self.get_change_type_display()} - {self.evaluation}"


# ========== OFFLINE SYNC QUEUE ==========

class OfflineMarkEntry(models.Model):
    """Queue for marks entered offline, synced when connected."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Sync'),
        ('synced', 'Successfully Synced'),
        ('conflict', 'Sync Conflict'),
        ('rejected', 'Rejected'),
    ]
    
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT)
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.PROTECT)
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)
    term = models.ForeignKey(Term, on_delete=models.PROTECT)
    
    # Grade data
    seq1_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    seq2_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mock_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    practical_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)
    
    # Sync metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_offline_at = models.DateTimeField()
    synced_at = models.DateTimeField(null=True, blank=True)
    synced_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Conflict resolution
    conflict_with_evaluation = models.ForeignKey(Evaluation, on_delete=models.SET_NULL, null=True, blank=True)
    teacher_conflict_choice = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['status', 'created_offline_at']
        indexes = [
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['created_offline_at']),
        ]
    
    def __str__(self):
        return f"Offline: {self.student.student_code} - {self.subject_assignment.subject.name}"


class MockExamSetting(models.Model):
    """Configuration for mock exam score blending (Phase 1.2.3).
    
    Allows schools to blend mock exam scores with final exam scores for advanced forms
    (FORM 5, FORM 7, UPPER 6, etc.). One setting per classroom/term combination.
    
    Default: 70% final exam + 30% mock exam score (disabled by default).
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="mock_exam_settings")
    classroom = models.ForeignKey("academics.Classroom", on_delete=models.CASCADE, related_name="mock_exam_settings")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="mock_exam_settings")
    
    # Weight configuration (must sum to 100% if is_active=True)
    final_weight = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Weight for final exam score (0-100%)"
    )
    mock_weight = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Weight for mock exam score (0-100%)"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Enable score blending for this classroom/term"
    )
    
    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("academic_year", "classroom", "term")
        indexes = [
            models.Index(fields=["academic_year", "classroom", "term"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return f"Mock Settings: {self.classroom.name} ({self.term.name})"
    
    def clean(self):
        """Validate that weights sum to 100% when active."""
        if self.is_active:
            total = self.final_weight + self.mock_weight
            if total != 100:
                raise ValidationError(
                    f"When active, weights must sum to 100%. Got: {total}% "
                    f"({self.final_weight}% final + {self.mock_weight}% mock)"
                )
    
    def save(self, *args, **kwargs):
        """Validate before saving."""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_for(cls, academic_year, classroom, term):
        """Get or create with defaults (disabled by default)."""
        setting, _ = cls.objects.get_or_create(
            academic_year=academic_year,
            classroom=classroom,
            term=term,
            defaults={
                "is_active": False,
                "final_weight": 70,
                "mock_weight": 30,
            }
        )
        return setting
