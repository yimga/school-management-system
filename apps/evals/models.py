from django.db import models
from django.core.exceptions import ValidationError

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
        term_label = self.term.get_name_display() if self.term_id else "All terms"
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
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="evaluations")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="evaluations")
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.PROTECT, related_name="evaluations")
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="evaluations")
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name="evaluations")

    # Backward compatible fields (old UI). New UI should use seq1/seq2.
    test1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    test2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Expanded components (Cameroon English sub-system + technical schools)
    seq1_score = models.DecimalField("Seq 1", max_digits=5, decimal_places=2, null=True, blank=True)
    seq2_score = models.DecimalField("Seq 2", max_digits=5, decimal_places=2, null=True, blank=True)
    exam_score = models.DecimalField("Exam", max_digits=5, decimal_places=2, null=True, blank=True)
    mock_score = models.DecimalField("Mock", max_digits=5, decimal_places=2, null=True, blank=True)
    practical_score = models.DecimalField("Practical", max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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
