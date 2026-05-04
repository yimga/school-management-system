# Pilot defect model (durable defect loop)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0058_tenant_retention_playbook_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="PilotDefect",
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
                ("title", models.CharField(max_length=240)),
                (
                    "source_school_slug",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Tenant slug or pilot slot label — no personal data.",
                        max_length=120,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                        ],
                        db_index=True,
                        default="medium",
                        max_length=16,
                    ),
                ),
                (
                    "module",
                    models.CharField(blank=True, db_index=True, max_length=64),
                ),
                (
                    "owner",
                    models.CharField(
                        blank=True,
                        help_text="Owning team or role label.",
                        max_length=120,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("reported", "Reported"),
                            ("triaged", "Triaged"),
                            ("in_progress", "In progress"),
                            ("fixed", "Fixed"),
                            ("verified", "Verified"),
                            ("deferred", "Deferred"),
                        ],
                        db_index=True,
                        default="reported",
                        max_length=20,
                    ),
                ),
                ("linked_test", models.CharField(blank=True, max_length=256)),
                (
                    "sot_batch",
                    models.CharField(
                        blank=True,
                        help_text="SOT forward-queue batch id (e.g. 11.4 batch number).",
                        max_length=64,
                    ),
                ),
                ("root_cause", models.TextField(blank=True)),
                ("regression_risk", models.CharField(blank=True, max_length=32)),
                (
                    "documented_exception",
                    models.TextField(
                        blank=True,
                        help_text="When fixed without automated test, document exception here.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Pilot defect",
                "verbose_name_plural": "Pilot defects",
                "ordering": ["-created_at"],
            },
        ),
    ]
