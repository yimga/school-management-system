"""Extracurricular clubs — non-sport student groups with advisors and rosters.

Metric 13 residual: athletics/extracurricular mandate requires clubs alongside
team/roster/sport. Clubs reuse the same school-scoped + advisor-assignment
discipline as Team/CoachAssignment, without sport/season/fixture machinery.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from apps.athletics.constants import DEFAULT_CLUB_CAPACITY


class ClubCategory(models.TextChoices):
    ACADEMIC = "academic", "Academic"
    ARTS = "arts", "Arts & culture"
    SERVICE = "service", "Service / community"
    STEM = "stem", "STEM"
    OTHER = "other", "Other"


class Club(models.Model):
    """A school-scoped extracurricular club (debate, robotics, choir, …)."""

    class Status(models.TextChoices):
        FORMING = "forming", "Forming"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        ARCHIVED = "archived", "Archived"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_clubs"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_clubs",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    category = models.CharField(
        max_length=16, choices=ClubCategory.choices, default=ClubCategory.OTHER
    )
    description = models.TextField(blank=True)
    meeting_day = models.CharField(max_length=48, blank=True)
    meeting_location = models.CharField(max_length=120, blank=True)
    capacity = models.PositiveSmallIntegerField(default=DEFAULT_CLUB_CAPACITY)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.FORMING
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["name"]
        unique_together = [("school", "slug")]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            base = slugify(self.name)[:120] or "club"
            candidate = base
            n = 2
            school_id = self.school_id
            while (
                school_id
                and Club.objects.filter(school_id=school_id, slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class ClubAdvisorAssignment(models.Model):
    """Links a staff user to a club they advise (object-level manage scope)."""

    class Role(models.TextChoices):
        LEAD = "lead", "Lead advisor"
        ASSISTANT = "assistant", "Assistant advisor"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_club_advisor_assignments",
    )
    club = models.ForeignKey(
        "athletics.Club", on_delete=models.CASCADE, related_name="advisor_assignments"
    )
    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="athletics_club_advisor_assignments",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.LEAD)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "advisor", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["club", "advisor"],
                condition=Q(is_active=True),
                name="uniq_active_advisor_per_club",
            )
        ]

    def __str__(self) -> str:
        return f"advisor {self.advisor_id} -> club {self.club_id} ({self.role})"


class ClubMembership(models.Model):
    """A student's place on a club roster."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WAITLIST = "waitlist", "Waitlist"
        LEFT = "left", "Left"

    ROSTER_ACTIVE_STATUSES = ("active", "waitlist")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_club_memberships",
    )
    club = models.ForeignKey(
        "athletics.Club", on_delete=models.CASCADE, related_name="memberships"
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="athletics_club_memberships",
    )
    role_title = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    joined_at = models.DateField(null=True, blank=True)
    left_at = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["club", "student_id"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["club", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["club", "student"],
                condition=Q(status__in=("active", "waitlist")),
                name="uniq_active_membership_per_club",
            ),
        ]

    def __str__(self) -> str:
        return f"club member {self.student_id} club {self.club_id} ({self.status})"


__all__ = [
    "Club",
    "ClubAdvisorAssignment",
    "ClubCategory",
    "ClubMembership",
]
