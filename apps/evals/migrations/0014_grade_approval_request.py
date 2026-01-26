from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ("academics", "0011_remove_scheduleentry_room_and_more"),
        ("people", "0017_studentprofile_user"),
        ("evals", "0013_alter_assessmentweights_unique_together_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GradeApprovalRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                    ),
                ),
                (
                    "entries",
                    models.JSONField(
                        blank=True,
                        default=list,
                    ),
                ),
                (
                    "summary",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending Review"),
                            ("UNDER_REVIEW", "Under Review"),
                            ("REVISION_REQUESTED", "Revision Requested"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="PENDING",
                        max_length=30,
                    ),
                ),
                (
                    "requested_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "reviewer_notes",
                    models.TextField(blank=True),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        related_name="grade_approval_requests",
                        to="people.teacherprofile",
                    ),
                ),
                (
                    "academic_year",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        related_name="grade_approval_requests",
                        to="academics.academicyear",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        related_name="grade_approval_requests",
                        to="academics.term",
                    ),
                ),
                (
                    "subject_assignment",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        related_name="grade_approval_requests",
                        to="academics.subjectassignment",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="grade_approval_requests_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="grade_approval_requests_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-requested_at"],
            },
        ),
    ]
