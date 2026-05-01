# Generated manually for governed saved reports.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    # FK is to schools.School (added in schools.0001_initial).
    dependencies = [
        ("analytics", "0015_student_at_risk_signal_br06"),
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GovernedSavedReport",
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
                ("name", models.CharField(max_length=200)),
                (
                    "definition",
                    models.JSONField(
                        default=dict,
                        help_text="Allowlisted keys only: dataset_id, fields, filters, group_by, aggregate, limit.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="governed_saved_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="governed_saved_reports",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="governedsavedreport",
            index=models.Index(
                fields=["school", "-updated_at"],
                name="analytics_gsr_school_updated_idx",
            ),
        ),
    ]
