# Generated for batch 1354 — zero-result content gap workflow

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0006_help_center_wave2_1346_1353"),
        ("portal", "0037_help_center_wave2_1346_1353"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HelpContentGapTask",
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
                ("query_fingerprint", models.CharField(db_index=True, max_length=64, unique=True)),
                ("hit_count", models.PositiveIntegerField(default=1)),
                ("due_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("assigned", "Assigned"),
                            ("drafted", "KB draft created"),
                            ("done", "Done"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=16,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="help_content_gap_tasks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "kb_draft_article",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="content_gap_tasks",
                        to="portal.kbarticle",
                    ),
                ),
            ],
            options={
                "ordering": ["-hit_count", "-updated_at"],
            },
        ),
    ]
