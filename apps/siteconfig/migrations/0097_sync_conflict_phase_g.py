# Global Powerhouse Phase G: SyncConflict model for offline delta-sync conflict tracking

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0003_schoolprovisioningevent"),
        ("accounts", "0001_initial"),
        ("siteconfig", "0096_phase_e_plan_addon_revenue_waiver"),
    ]

    operations = [
        migrations.CreateModel(
            name="SyncConflict",
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
                    "entity_type",
                    models.CharField(
                        help_text="e.g. student, attendance, classroom", max_length=40
                    ),
                ),
                (
                    "entity_id",
                    models.BigIntegerField(
                        help_text="Primary key of the conflicted record"
                    ),
                ),
                (
                    "client_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Client/offline version of changed fields",
                    ),
                ),
                (
                    "server_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Current server version of the record (relevant fields)",
                    ),
                ),
                ("client_updated_at", models.DateTimeField(blank=True, null=True)),
                ("server_updated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("RESOLVED_SERVER", "Kept server version"),
                            ("RESOLVED_CLIENT", "Kept client version"),
                            ("RESOLVED_MERGE", "Merged manually"),
                            ("DISCARDED", "Discarded"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolution_note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="resolved_sync_conflicts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reported_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="reported_sync_conflicts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sync_conflicts",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sync conflict",
                "verbose_name_plural": "Sync conflicts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="syncconflict",
            index=models.Index(
                fields=["school", "status"], name="siteconfig_s_school__a0e0b4_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="syncconflict",
            index=models.Index(
                fields=["entity_type", "entity_id"],
                name="siteconfig_s_entity__b1f1c5_idx",
            ),
        ),
    ]
