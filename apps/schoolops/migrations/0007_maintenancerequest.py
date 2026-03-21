# Wave 17 — facilities maintenance requests

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0006_rename_schools_vis_school_i_idx_schools_vis_school__6167ff_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MaintenanceRequest",
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
                ("title", models.CharField(max_length=200)),
                ("location", models.CharField(blank=True, max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("in_progress", "In progress"),
                            ("closed", "Closed"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reported_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maintenance_requests_reported",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maintenance_requests",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schools_maintenancerequest",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="maintenancerequest",
            index=models.Index(
                fields=["school", "status"],
                name="schools_mai_school_i_idx",
            ),
        ),
    ]
