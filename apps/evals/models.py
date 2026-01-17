from django.db import models
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear, Term, SubjectAssignment
from apps.people.models import TeacherProfile, StudentProfile


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

    test1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    test2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    @property
    def total_score(self) -> float:
        """Single score used for ranking/statistics.

        For now: average of test1 and test2 when present.
        This is intentionally simple so we can evolve to weighted
        sequences/exams/mocks/practicals later.
        """
        scores = []
        if self.test1 is not None:
            scores.append(float(self.test1))
        if self.test2 is not None:
            scores.append(float(self.test2))
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 2)

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
