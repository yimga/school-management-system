"""v4.00.43 — Support net-new scope.

Additive:
  - SupportOnCallShift (new) — primary/backup on-call rotation rows.
  - PublicIncident (new) — operator-promoted public outage entries shown at /status/.
"""

from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0188_support_attachments_and_linking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportOnCallShift",
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
                (
                    "role_tag",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional grouping (e.g. 'platform', 'billing').",
                        max_length=40,
                    ),
                ),
                ("is_primary", models.BooleanField(db_index=True, default=True)),
                ("starts_at", models.DateTimeField(db_index=True)),
                ("ends_at", models.DateTimeField(db_index=True)),
                ("notes", models.CharField(blank=True, default="", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="support_on_call_shifts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Support on-call shift",
                "verbose_name_plural": "Support on-call shifts",
                "ordering": ["-starts_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["starts_at", "ends_at"],
                        name="siteconfig__starts_a_5a2b91_idx",
                    ),
                    models.Index(
                        fields=["is_primary", "starts_at"],
                        name="siteconfig__is_prim_4f8d27_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PublicIncident",
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
                ("title", models.CharField(max_length=180)),
                ("summary", models.TextField(blank=True, default="")),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("MINOR", "Minor"),
                            ("MAJOR", "Major"),
                            ("CRITICAL", "Critical"),
                        ],
                        default="MINOR",
                        max_length=12,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("INVESTIGATING", "Investigating"),
                            ("IDENTIFIED", "Identified"),
                            ("MONITORING", "Monitoring"),
                            ("RESOLVED", "Resolved"),
                        ],
                        default="INVESTIGATING",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField()),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "promoted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promoted_public_incidents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_ticket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="public_incidents",
                        to="siteconfig.globalsupportticket",
                    ),
                ),
            ],
            options={
                "verbose_name": "Public incident",
                "verbose_name_plural": "Public incidents",
                "ordering": ["-started_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["status", "-started_at"],
                        name="siteconfig__status__7c2f4e_idx",
                    ),
                    models.Index(
                        fields=["-started_at"],
                        name="siteconfig__started_a3b91d_idx",
                    ),
                ],
            },
        ),
    ]
