# §11.4 Phase B — audit rows for inbound platform integration webhooks (HMAC).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0034_runtimedefaults_webhook_signing_secret_first_class"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformIntegrationWebhookEvent",
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
                    "received_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "verified",
                    models.BooleanField(db_index=True, default=False),
                ),
                (
                    "event_type",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "body_sha256",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "client_ip",
                    models.CharField(blank=True, default="", max_length=45),
                ),
            ],
            options={
                "verbose_name": "Integration webhook event",
                "verbose_name_plural": "Integration webhook events",
                "db_table": "platform_runtime_integration_webhook_event",
                "ordering": ["-received_at"],
            },
        ),
    ]
