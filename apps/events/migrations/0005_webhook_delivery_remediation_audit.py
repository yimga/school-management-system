# DLQ operator disposition + remediation audit trail

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("events", "0004_domain_event_schema_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookdelivery",
            name="operator_resolution",
            field=models.CharField(
                blank=True,
                choices=[("resolved", "Resolved"), ("ignored", "Ignored")],
                db_index=True,
                help_text="Operator DLQ disposition; null means open on dead-letter rows.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="webhookdelivery",
            name="operator_resolution_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="webhookdelivery",
            name="operator_resolution_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="webhookdelivery",
            name="operator_resolution_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="EventSystemRemediationAudit",
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
                ("school_id", models.UUIDField(db_index=True)),
                (
                    "delivery_source",
                    models.CharField(
                        choices=[
                            ("domain_webhook", "Domain webhook delivery"),
                            ("platform_webhook", "Platform webhook delivery"),
                        ],
                        max_length=32,
                    ),
                ),
                ("delivery_pk", models.PositiveBigIntegerField()),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("retry", "Retry"),
                            ("resolved", "Marked resolved"),
                            ("ignored", "Marked ignored"),
                        ],
                        max_length=16,
                    ),
                ),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Event system remediation audit",
                "verbose_name_plural": "Event system remediation audits",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="eventsystemremediationaudit",
            index=models.Index(
                fields=["school_id", "created_at"],
                name="events_remed_school_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="eventsystemremediationaudit",
            index=models.Index(
                fields=["delivery_source", "delivery_pk"],
                name="events_remed_src_pk_idx",
            ),
        ),
    ]
