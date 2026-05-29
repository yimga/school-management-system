"""Staff compliance registry — clearance expiry blocks attendance (Phase 4F)."""

from __future__ import annotations

from datetime import date

from django.db import models


class StaffComplianceRecord(models.Model):
    """Jurisdiction-scoped clearance / safeguarding record per teacher."""

    class ClearanceType(models.TextChoices):
        SAFEGUARDING = "safeguarding", "Safeguarding / background check"
        MEDICAL = "medical", "Occupational health"
        LICENSE = "license", "Professional license"
        OTHER = "other", "Other clearance"

    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="compliance_records",
    )
    clearance_type = models.CharField(
        max_length=32,
        choices=ClearanceType.choices,
        default=ClearanceType.SAFEGUARDING,
    )
    jurisdiction_code = models.CharField(
        max_length=8,
        blank=True,
        help_text="ISO country or subdivision code scoping this clearance.",
    )
    expires_on = models.DateField(null=True, blank=True)
    is_cleared = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-expires_on", "clearance_type")
        verbose_name = "Staff compliance record"
        verbose_name_plural = "Staff compliance records"

    def __str__(self) -> str:
        return f"{self.teacher_id} {self.clearance_type} ({self.jurisdiction_code})"

    def is_valid_on(self, check_date: date | None = None) -> bool:
        if not self.is_cleared:
            return False
        if self.expires_on is None:
            return True
        effective = check_date or date.today()
        return self.expires_on >= effective


def attendance_allowed_for_teacher(teacher, check_date: date | None = None) -> tuple[bool, str]:
    """
    Return ``(allowed, reason)`` for teacher attendance on ``check_date``.

    Any expired or revoked safeguarding clearance blocks attendance.
    """
    if teacher is None:
        return False, "teacher_missing"
    effective = check_date or date.today()
    records = StaffComplianceRecord.objects.filter(
        teacher=teacher,
        clearance_type=StaffComplianceRecord.ClearanceType.SAFEGUARDING,
    )
    if not records.exists():
        return True, "no_safeguarding_requirement"
    for record in records:
        if not record.is_valid_on(effective):
            return False, f"clearance_expired:{record.pk}"
    return True, "cleared"
