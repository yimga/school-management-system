"""Transaction-driven instruction-day ledger (Phase 4E)."""

from __future__ import annotations

from django.db import models


class InstructionDay(models.Model):
    """Per-school ledger of instructional vs non-instructional calendar days."""

    class EventKind(models.TextChoices):
        INSTRUCTIONAL = "instructional", "Instructional day"
        HOLIDAY = "holiday", "Holiday / no school"
        STAFF_ONLY = "staff_only", "Staff development (no students)"
        EXAM = "exam", "Examination day"
        CLOSED = "closed", "Campus closed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="instruction_days",
    )
    calendar_date = models.DateField()
    event_kind = models.CharField(
        max_length=20,
        choices=EventKind.choices,
        default=EventKind.INSTRUCTIONAL,
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("school", "calendar_date")]
        ordering = ("-calendar_date",)
        verbose_name = "Instruction day"
        verbose_name_plural = "Instruction days"

    def __str__(self) -> str:
        return f"{self.school_id} {self.calendar_date} ({self.event_kind})"

    @property
    def is_instructional(self) -> bool:
        return self.event_kind == self.EventKind.INSTRUCTIONAL


def is_instructional_day(school, calendar_date) -> bool:
    """Return True when no ledger row exists (default instructional) or row is instructional."""
    if school is None or calendar_date is None:
        return True
    row = InstructionDay.objects.filter(school=school, calendar_date=calendar_date).first()
    if row is None:
        return True
    return row.is_instructional
