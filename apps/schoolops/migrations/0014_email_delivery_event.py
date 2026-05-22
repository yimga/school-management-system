"""v3.57.x Wave 8 Agent C — Add EmailDeliveryEvent append-only log.

Pure CreateModel — no live-model imports (scan_migration_model_imports
zero-tolerance gate). The model is platform-level (NOT tenant-scoped);
the operator email-health dashboard wants cross-tenant aggregates and
the per-tenant correlation is intentionally collapsed via
sha256(recipient)[:12].
"""
from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0013_meal_plan_balance_notification_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailDeliveryEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        help_text=(
                            "UUIDv4 primary key. Random so event IDs don't "
                            "leak ordering or per-tenant volume."
                        ),
                    ),
                ),
                (
                    "to_hash",
                    models.CharField(
                        db_index=True,
                        max_length=12,
                        help_text=(
                            "First 12 hex chars of sha256(recipient_email). "
                            "Used to correlate retries to a single recipient "
                            "WITHOUT persisting the raw address."
                        ),
                    ),
                ),
                (
                    "subject_prefix",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        help_text=(
                            "First 64 chars of the subject line, redacted "
                            "by the caller. Stored verbatim — the caller's "
                            "responsibility to strip anything PII-shaped "
                            "before record()."
                        ),
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        default="transactional",
                        max_length=24,
                        help_text=(
                            "Send priority class: 'transactional' or 'bulk'."
                        ),
                    ),
                ),
                (
                    "attempts",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text=(
                            "Number of SMTP send attempts made for this event "
                            "(1..N where N is the retry backoff length)."
                        ),
                    ),
                ),
                (
                    "ok",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "True iff the final SMTP attempt returned without "
                            "raising. False if every attempt raised."
                        ),
                    ),
                ),
                (
                    "error_kind",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        help_text=(
                            "One of 'smtp_exception' | 'os_error' | "
                            "'connection_error' | 'value_error' | '' "
                            "(success). Coarse-grained on purpose."
                        ),
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text=(
                            "Wall-clock time of the LAST attempt "
                            "(success or failure)."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Email delivery event",
                "verbose_name_plural": "Email delivery events",
                "db_table": "schoolops_email_delivery_event",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="emaildeliveryevent",
            index=models.Index(
                fields=["to_hash", "created_at"],
                name="schoolops_em_to_hash_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="emaildeliveryevent",
            index=models.Index(
                fields=["ok", "created_at"],
                name="schoolops_em_ok_created_idx",
            ),
        ),
    ]
