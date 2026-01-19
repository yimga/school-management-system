from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, Term, Classroom


class GradingDeadline(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="grading_deadlines",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="grading_deadlines",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grading_deadlines",
    )
    deadline_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("academic_year", "term", "classroom")
        ordering = ["-deadline_at"]

    def __str__(self) -> str:
        scope = self.classroom.name if self.classroom else "Whole school"
        date_label = timezone.localtime(self.deadline_at).strftime("%Y-%m-%d %H:%M")
        return f"{self.academic_year} {self.term.get_name_display()} - {scope}: {date_label}"
