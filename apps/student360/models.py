"""
Student 360 models (Section 15.1).
Immutable transcript: once frozen, the snapshot is never updated — cross-year archive is read-only.
"""

from django.conf import settings
from django.db import models


class ImmutableTranscript(models.Model):
    """
    Immutable snapshot of a student's transcript for one academic year.
    Created by an explicit "freeze" action; never updated in place.
    Used for cross-year archive view and audit/compliance.
    """

    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="immutable_transcripts",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="immutable_transcripts",
    )
    snapshot = models.JSONField(
        help_text="Frozen transcript data: scores, terms, ranks, metadata (region, language).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_immutable_transcripts",
    )

    class Meta:
        ordering = ["-academic_year__start_date", "-created_at"]
        # One canonical frozen transcript per student per academic year (latest freeze wins for display)
        unique_together = [["student", "academic_year"]]
        verbose_name = "Immutable transcript"
        verbose_name_plural = "Immutable transcripts"

    def __str__(self):
        return f"Transcript {self.student_id} · {self.academic_year}"
