"""TenantReactivationAttempt for the 4-cadence win-back campaign (v4.00.98 Phase 4)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0077_newsletter_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantReactivationAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("school_id", models.CharField(db_index=True, max_length=40)),
                ("school_name", models.CharField(blank=True, default="", max_length=160)),
                ("recipient_email", models.CharField(blank=True, default="", max_length=254)),
                ("recipient_email_hash", models.CharField(blank=True, default="", max_length=16)),
                ("cadence", models.CharField(
                    choices=[
                        ("30d", "30 days inactive"),
                        ("60d", "60 days inactive"),
                        ("90d", "90 days inactive"),
                        ("120d", "120 days inactive (final)"),
                    ],
                    db_index=True, max_length=8,
                )),
                ("sent_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("delivery_event_id", models.CharField(blank=True, default="", max_length=64)),
                ("delivery_ok", models.BooleanField(default=True)),
                ("delivery_error_kind", models.CharField(blank=True, default="", max_length=64)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("replied_at", models.DateTimeField(blank=True, null=True)),
                ("converted_back_at", models.DateTimeField(blank=True, null=True)),
                ("suppressed", models.BooleanField(default=False)),
                ("suppressed_reason", models.CharField(blank=True, default="", max_length=64)),
            ],
            options={
                "verbose_name": "Tenant reactivation attempt",
                "verbose_name_plural": "Tenant reactivation attempts",
                "ordering": ["-sent_at"],
            },
        ),
        migrations.AddIndex(
            model_name="tenantreactivationattempt",
            index=models.Index(fields=["school_id", "cadence", "-sent_at"], name="treact_school_cadence_idx"),
        ),
        migrations.AddIndex(
            model_name="tenantreactivationattempt",
            index=models.Index(fields=["cadence", "-sent_at"], name="treact_cadence_sent_idx"),
        ),
        migrations.AddConstraint(
            model_name="tenantreactivationattempt",
            constraint=models.UniqueConstraint(
                fields=("school_id", "cadence"),
                condition=models.Q(suppressed=False),
                name="treact_unique_school_cadence_not_suppressed",
            ),
        ),
    ]
