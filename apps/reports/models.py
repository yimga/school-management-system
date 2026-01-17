from django.db import models
from apps.academics.models import AcademicYear, Term, ClassRoom
from apps.people.models import StudentProfile
from apps.accounts.models import User


class TermPublishStatus(models.Model):
    """
    If classroom is NULL, it means published for the entire school for that term.
    If classroom is set, publish applies only to that class.
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="publish_statuses")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="publish_statuses")
    classroom = models.ForeignKey(ClassRoom, null=True, blank=True, on_delete=models.CASCADE, related_name="publish_statuses")

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="publishes")

    class Meta:
        unique_together = ("academic_year", "term", "classroom")

    def __str__(self):
        scope = self.classroom.name if self.classroom else "Whole school"
        return f"{self.academic_year} {self.term.get_name_display()} - {scope}: {'PUBLISHED' if self.is_published else 'NOT'}"


class ReportCard(models.Model):
    class Type(models.TextChoices):
        TERM = "TERM", "Term"
        ANNUAL = "ANNUAL", "Annual"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="report_cards")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.CASCADE, related_name="report_cards")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="report_cards")

    type = models.CharField(max_length=10, choices=Type.choices)
    pdf_file = models.FileField(upload_to="reportcards/", null=True, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.student} - {self.type} - {self.academic_year}"

