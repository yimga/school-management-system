# Generated for batch 1518 — public status incidents

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("observability", "0003_friction_event_g5"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformStatusIncident",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("investigating", "Investigating"),
                            ("identified", "Identified"),
                            ("monitoring", "Monitoring"),
                            ("resolved", "Resolved"),
                        ],
                        db_index=True,
                        default="investigating",
                        max_length=24,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("critical", "Critical"),
                        ],
                        db_index=True,
                        default="medium",
                        max_length=16,
                    ),
                ),
                (
                    "component_keys",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Component keys from public status payload (e.g. payments, auth).",
                    ),
                ),
                ("is_public", models.BooleanField(db_index=True, default=True)),
                (
                    "started_at",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_status_incidents_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["is_public", "status", "-started_at"],
                        name="observabili_is_publ_4a8f2a_idx",
                    )
                ],
            },
        ),
    ]
