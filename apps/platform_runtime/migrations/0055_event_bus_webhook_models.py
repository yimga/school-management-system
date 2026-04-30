# Generated manually — event bus webhooks (EventWebhookSubscription / EventWebhookDelivery) + PlatformEvent proxy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0054_offlineaction_notes_report_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformEvent",
            fields=[],
            options={
                "verbose_name": "Platform event",
                "verbose_name_plural": "Platform events",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("platform_runtime.platformeventlog",),
        ),
        migrations.CreateModel(
            name="EventWebhookSubscription",
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
                ("name", models.CharField(blank=True, max_length=120)),
                (
                    "tenant_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                (
                    "school_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=40),
                ),
                ("target_url", models.URLField(max_length=2048)),
                (
                    "secret",
                    models.CharField(
                        blank=True,
                        help_text="Shared secret for X-RMC-Signature (HMAC-SHA256 hex of raw body).",
                        max_length=256,
                    ),
                ),
                (
                    "event_types",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of event_type strings to deliver; empty means all types.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Event webhook subscription",
                "verbose_name_plural": "Event webhook subscriptions",
                "db_table": "platform_runtime_eventwebhooksubscription",
            },
        ),
        migrations.CreateModel(
            name="EventWebhookDelivery",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("delivering", "Delivering"),
                            ("delivered", "Delivered"),
                            ("failed", "Failed"),
                            ("dead_letter", "Dead letter"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("last_http_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "platform_event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="webhook_deliveries",
                        to="platform_runtime.platformeventlog",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="platform_runtime.eventwebhooksubscription",
                    ),
                ),
            ],
            options={
                "verbose_name": "Event webhook delivery",
                "verbose_name_plural": "Event webhook deliveries",
                "db_table": "platform_runtime_eventwebhookdelivery",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="eventwebhookdelivery",
            index=models.Index(
                fields=["status", "next_retry_at"],
                name="platform_ru_status_64f0ee_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="eventwebhookdelivery",
            index=models.Index(
                fields=["platform_event", "subscription"],
                name="platform_ru_platfor_8e8c2e_idx",
            ),
        ),
    ]
