# Generated manually for platform_surfaces_explainer sticky notes slice.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0038_advancement_donor_gift"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("people", "0048_alter_passportdocument_file_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentNote",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("note", "Note"),
                            ("report", "Report"),
                            ("quick_capture", "Quick capture"),
                        ],
                        default="note",
                        max_length=48,
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=200)),
                ("body", models.TextField()),
                (
                    "client_offline_id",
                    models.CharField(
                        blank=True,
                        help_text="Idempotency key from offline queue payload.",
                        max_length=64,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="student_notes_authored",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_notes",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_notes",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student note",
                "verbose_name_plural": "Student notes",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="studentnote",
            index=models.Index(
                fields=["school", "-created_at"],
                name="people_stud_school__8f0a2d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="studentnote",
            index=models.Index(
                fields=["student", "-created_at"],
                name="people_stud_student_4c1e8a_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentnote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id__gt", "")),
                fields=("school", "client_offline_id"),
                name="people_studentnote_school_client_offline_uniq",
            ),
        ),
    ]
