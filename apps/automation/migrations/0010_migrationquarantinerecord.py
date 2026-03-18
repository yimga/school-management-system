# Repair and quarantine engine: quarantine records for guided repair

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0009_migrationplaybook"),
        ("schools", "0012_seed_default_gilead_school"),
    ]

    operations = [
        migrations.CreateModel(
            name="MigrationQuarantineRecord",
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
                ("domain", models.CharField(db_index=True, max_length=32)),
                (
                    "row_index",
                    models.PositiveIntegerField(
                        help_text="1-based row index in source."
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        blank=True, default=dict, help_text="Row data (sanitized)."
                    ),
                ),
                ("issue_class", models.CharField(db_index=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        db_index=True,
                        max_length=20,
                        choices=[
                            ("PENDING", "Pending"),
                            ("REPAIRED", "Repaired"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "resolution_payload",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Repaired row or resolution note.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "migration_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="quarantine_records",
                        to="automation.migrationrun",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="migration_quarantine_records",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Migration quarantine record",
                "verbose_name_plural": "Migration quarantine records",
            },
        ),
        migrations.AddIndex(
            model_name="migrationquarantinerecord",
            index=models.Index(
                fields=["school", "domain", "status"],
                name="automation_quarantine_school_domain_status_idx",
            ),
        ),
    ]
