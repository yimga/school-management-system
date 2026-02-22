# Phase Compliance (plan 3.9): RegionFeatureCompliance for ComplianceGuardMiddleware

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0008_change_accesslog_timestamp"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegionFeatureCompliance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "feature_code",
                    models.CharField(
                        help_text="e.g. Right_to_Erasure, Export_All_Student_Data, COPPA_consent",
                        max_length=80,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ENABLED", "Enabled"),
                            ("DISABLED", "Disabled"),
                            ("RESTRICTED", "Restricted (block with structured error)"),
                        ],
                        default="ENABLED",
                        max_length=20,
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_compliance_rules",
                        to="siteconfig.regionconfig",
                    ),
                ),
            ],
            options={
                "verbose_name": "Region feature compliance",
                "verbose_name_plural": "Region feature compliance rules",
                "ordering": ["region", "feature_code"],
                "unique_together": {("region", "feature_code")},
            },
        ),
    ]
