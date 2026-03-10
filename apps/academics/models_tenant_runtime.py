from __future__ import annotations

from django.conf import settings
from django.db import models


class ReportCardStyleAssignment(models.Model):
    classroom = models.OneToOneField(
        "academics.Classroom",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="report_card_style_assignment",
    )
    style = models.ForeignKey(
        "siteconfig.ReportCardStyle",
        on_delete=models.PROTECT,
        related_name="assignments",
    )

    class Meta:
        app_label = "academics"
        db_table = "siteconfig_reportcardstyleassignment"
        ordering = ["classroom__name"]

    def __str__(self):
        return f"{self.classroom} -> {self.style.name}"


class HolidayCalendar(models.Model):
    HOLIDAY_TYPE_CHOICES = [
        ("school_holiday", "School Holiday"),
        ("public_holiday", "Public Holiday"),
        ("exam_period", "Exam Period"),
        ("religious", "Religious Holiday"),
        ("special_event", "Special Event"),
    ]

    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.CASCADE,
        related_name="holidays",
        help_text="Region this holiday applies to",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="holidays_by_region",
        help_text="Academic year for this holiday",
    )
    name = models.CharField(
        max_length=200,
        help_text="Holiday name (e.g., 'Christmas Break', 'Eid al-Fitr')",
    )
    date_start = models.DateField(help_text="Holiday start date")
    date_end = models.DateField(help_text="Holiday end date (inclusive)")
    holiday_type = models.CharField(
        max_length=50,
        choices=HOLIDAY_TYPE_CHOICES,
        help_text="Type of holiday",
    )
    is_working_day = models.BooleanField(
        default=False,
        help_text="Some regions work during certain holidays (e.g., religious holidays)",
    )
    description = models.TextField(blank=True, help_text="Holiday description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "academics"
        db_table = "siteconfig_holidaycalendar"
        ordering = ["date_start"]
        unique_together = ("region", "academic_year", "name")

    def __str__(self):
        return f"{self.region.code} - {self.name} ({self.date_start.year})"

    def overlaps_date(self, date):
        return self.date_start <= date <= self.date_end


class RolloverProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        APPLIED = "APPLIED", "Applied"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="rollover_proposals",
    )
    source_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="rollover_proposals_as_source",
    )
    target_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="rollover_proposals_as_target",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rollover_proposals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_rollover_proposals",
    )
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "academics"
        db_table = "accounts_rolloverproposal"
        ordering = ["-created_at"]
        verbose_name = "Rollover proposal"
        verbose_name_plural = "Rollover proposals"

    def __str__(self):
        return f"{self.school.name}: {self.source_year.name} -> {self.target_year.name} ({self.status})"


class RolloverProposalItem(models.Model):
    proposal = models.ForeignKey(
        "academics.RolloverProposal",
        on_delete=models.CASCADE,
        related_name="items",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="rollover_proposal_items",
    )
    current_classroom_id = models.PositiveIntegerField(null=True, blank=True)
    suggested_next_classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="rollover_items_suggested",
    )
    approved_next_classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="rollover_items_approved",
    )
    promotion_status = models.CharField(max_length=20, blank=True)
    annual_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    outstanding_returns = models.PositiveIntegerField(default=0)
    is_graduate = models.BooleanField(
        default=False,
        help_text="If True, student will be marked Alumni and removed from active roll.",
    )

    class Meta:
        app_label = "academics"
        db_table = "accounts_rolloverproposalitem"
        ordering = ["proposal", "student"]
        verbose_name = "Rollover proposal item"
        verbose_name_plural = "Rollover proposal items"

    def __str__(self):
        return f"{self.student} -> {self.approved_next_classroom or self.suggested_next_classroom} ({self.promotion_status})"
