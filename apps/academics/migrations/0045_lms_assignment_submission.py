"""Education-system phase 2 (2026-05-11): LMS spine.

Adds canonical `LMSAssignment` + `LMSSubmission` so future LMS surfaces
(assignment hub, gradebook v2, plagiarism checks) have a single home.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _lms_tenant_upload_to(subpath):
    """Tenant-prefixed upload_to mirroring people._people_tenant_upload_to.

    Inlined from ``_lms_tenant_upload_to`` for
    migration historical-state safety.
    """

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None)
        if school_id is None:
            assignment = getattr(instance, "assignment", None)
            school_id = getattr(assignment, "school_id", None)
        bucket = f"tenant-{school_id or 'unscoped'}"
        return f"{bucket}/{subpath}/{filename}"

    return upload_to


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0044_generalize_certification_board_choices"),
        ("schools", "0001_initial"),
        ("people", "0046_specialeducationplan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LMSAssignment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("instructions", models.TextField(blank=True)),
                ("assignment_type", models.CharField(
                    choices=[
                        ("HOMEWORK", "Homework"),
                        ("QUIZ", "Quiz"),
                        ("PROJECT", "Project"),
                        ("ESSAY", "Essay"),
                        ("LAB", "Lab / practical"),
                        ("PARTICIPATION", "Participation / discussion"),
                        ("OTHER", "Other"),
                    ],
                    default="HOMEWORK",
                    max_length=16,
                )),
                ("status", models.CharField(
                    choices=[
                        ("DRAFT", "Draft"),
                        ("PUBLISHED", "Published"),
                        ("CLOSED", "Closed for submissions"),
                        ("GRADED", "Graded"),
                        ("ARCHIVED", "Archived"),
                    ],
                    default="DRAFT",
                    max_length=16,
                )),
                ("points_possible", models.DecimalField(decimal_places=2, default=100, max_digits=6)),
                ("weight", models.DecimalField(decimal_places=2, default=1, max_digits=5)),
                ("available_at", models.DateTimeField(blank=True, null=True)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("late_penalty_pct", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("attachment", models.FileField(
                    blank=True,
                    null=True,
                    upload_to=_lms_tenant_upload_to("lms_assignment_attachments"),
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classroom", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lms_assignments",
                    to="academics.classroom",
                )),
                ("school", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lms_assignments",
                    to="schools.school",
                )),
                ("subject", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lms_assignments",
                    to="academics.subject",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lms_assignments",
                    to="people.teacherprofile",
                )),
                ("term", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lms_assignments",
                    to="academics.term",
                )),
            ],
            options={
                "verbose_name": "LMS assignment",
                "verbose_name_plural": "LMS assignments",
                "ordering": ["-due_at", "-id"],
                "indexes": [
                    models.Index(fields=["school", "classroom", "status"], name="lms_assign_scs_idx"),
                    models.Index(fields=["teacher", "-due_at"], name="lms_assign_teacher_due_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LMSSubmission",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("NOT_SUBMITTED", "Not submitted"),
                        ("DRAFT", "Draft"),
                        ("SUBMITTED", "Submitted"),
                        ("LATE", "Submitted late"),
                        ("GRADED", "Graded"),
                        ("RETURNED", "Returned for revision"),
                        ("EXCUSED", "Excused"),
                    ],
                    default="NOT_SUBMITTED",
                    max_length=16,
                )),
                ("content", models.TextField(blank=True)),
                ("attachment", models.FileField(
                    blank=True,
                    null=True,
                    upload_to=_lms_tenant_upload_to("lms_submission_attachments"),
                )),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("feedback", models.TextField(blank=True)),
                ("graded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignment", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="submissions",
                    to="academics.lmsassignment",
                )),
                ("graded_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="lms_submissions_graded",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("school", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lms_submissions",
                    to="schools.school",
                )),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lms_submissions",
                    to="people.studentprofile",
                )),
            ],
            options={
                "verbose_name": "LMS submission",
                "verbose_name_plural": "LMS submissions",
                "ordering": ["-submitted_at", "-id"],
                "unique_together": {("assignment", "student")},
                "indexes": [
                    models.Index(fields=["school", "assignment", "status"], name="lms_sub_sas_idx"),
                    models.Index(fields=["student", "-submitted_at"], name="lms_sub_student_sub_idx"),
                ],
            },
        ),
    ]
