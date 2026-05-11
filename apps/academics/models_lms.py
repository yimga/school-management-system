"""Education-system phase 2 (2026-05-11): LMS spine — `LMSAssignment` + `LMSSubmission`.

Closes the SOT roadmap gap "Assignment + Submission LMS spine". This is the
minimal canonical pair other apps can wire to (Google Classroom-style flow):
teacher creates an assignment for a classroom; students submit a response;
teacher grades the submission, which then materializes a row into the
existing `evals.Evaluation` table.

Names are `LMSAssignment` / `LMSSubmission` to avoid collision with the
existing `academics.SubjectAssignment` (which is a roster row, not a piece
of work) and `evals.TeacherAssignment` (assignment of a teacher to a
subject_assignment). Future LMS surfaces (rubrics, peer review, plagiarism
checks) hang off these two roots.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _lms_tenant_upload_to(subpath):
    """Tenant-prefixed upload_to mirroring people._people_tenant_upload_to."""

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None)
        if school_id is None:
            assignment = getattr(instance, "assignment", None)
            school_id = getattr(assignment, "school_id", None)
        bucket = f"tenant-{school_id or 'unscoped'}"
        return f"{bucket}/{subpath}/{filename}"

    return upload_to


class LMSAssignment(models.Model):
    """A unit of work assigned to one classroom by one teacher."""

    class AssignmentType(models.TextChoices):
        HOMEWORK = "HOMEWORK", _("Homework")
        QUIZ = "QUIZ", _("Quiz")
        PROJECT = "PROJECT", _("Project")
        ESSAY = "ESSAY", _("Essay")
        LAB = "LAB", _("Lab / practical")
        PARTICIPATION = "PARTICIPATION", _("Participation / discussion")
        OTHER = "OTHER", _("Other")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        PUBLISHED = "PUBLISHED", _("Published")
        CLOSED = "CLOSED", _("Closed for submissions")
        GRADED = "GRADED", _("Graded")
        ARCHIVED = "ARCHIVED", _("Archived")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lms_assignments",
    )
    classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.CASCADE,
        related_name="lms_assignments",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.PROTECT,
        related_name="lms_assignments",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lms_assignments",
    )
    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.PROTECT,
        related_name="lms_assignments",
    )

    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    assignment_type = models.CharField(
        max_length=16, choices=AssignmentType.choices, default=AssignmentType.HOMEWORK
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    points_possible = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=100,
        help_text=_("Max points; ignored if the school uses a non-numeric grading scale."),
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        help_text=_("Multiplier applied when feeding the submission grade into the term composite."),
    )
    available_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    late_penalty_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_("Percentage docked per day late (0 disables)."),
    )
    attachment = models.FileField(
        upload_to=_lms_tenant_upload_to("lms_assignment_attachments"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-due_at", "-id"]
        verbose_name = _("LMS assignment")
        verbose_name_plural = _("LMS assignments")
        indexes = [
            models.Index(fields=["school", "classroom", "status"]),
            models.Index(fields=["teacher", "-due_at"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.classroom_id}"

    @property
    def is_open_for_submissions(self) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        now = timezone.now()
        if self.available_at and now < self.available_at:
            return False
        return True


class LMSSubmission(models.Model):
    """One student's response to an LMSAssignment."""

    class Status(models.TextChoices):
        NOT_SUBMITTED = "NOT_SUBMITTED", _("Not submitted")
        DRAFT = "DRAFT", _("Draft")
        SUBMITTED = "SUBMITTED", _("Submitted")
        LATE = "LATE", _("Submitted late")
        GRADED = "GRADED", _("Graded")
        RETURNED = "RETURNED", _("Returned for revision")
        EXCUSED = "EXCUSED", _("Excused")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lms_submissions",
    )
    assignment = models.ForeignKey(
        LMSAssignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="lms_submissions",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.NOT_SUBMITTED
    )
    content = models.TextField(blank=True, help_text=_("Text body of the submission."))
    attachment = models.FileField(
        upload_to=_lms_tenant_upload_to("lms_submission_attachments"),
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lms_submissions_graded",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("assignment", "student")]
        ordering = ["-submitted_at", "-id"]
        verbose_name = _("LMS submission")
        verbose_name_plural = _("LMS submissions")
        indexes = [
            models.Index(fields=["school", "assignment", "status"]),
            models.Index(fields=["student", "-submitted_at"]),
        ]

    def __str__(self):
        return f"{self.assignment_id} / {self.student_id} ({self.status})"

    def mark_submitted(self) -> None:
        now = timezone.now()
        self.submitted_at = now
        due = self.assignment.due_at
        self.status = self.Status.LATE if (due and now > due) else self.Status.SUBMITTED
