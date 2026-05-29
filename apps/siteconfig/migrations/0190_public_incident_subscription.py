"""v4.00.45 — Anonymous opt-in email subscriptions for the public status page."""

from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0189_support_oncall_publicincident"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicIncidentSubscription",
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
                ("email", models.EmailField(max_length=240, unique=True)),
                ("verification_token", models.CharField(max_length=64, unique=True)),
                ("unsubscribe_token", models.CharField(max_length=64, unique=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("unsubscribed_at", models.DateTimeField(blank=True, null=True)),
                ("last_alerted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Public incident subscription",
                "verbose_name_plural": "Public incident subscriptions",
                "ordering": ["-created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["confirmed_at"],
                        name="siteconfig__confirm_8a1f4d_idx",
                    ),
                    models.Index(
                        fields=["unsubscribed_at"],
                        name="siteconfig__unsub_b2d54e_idx",
                    ),
                ],
            },
        ),
    ]
