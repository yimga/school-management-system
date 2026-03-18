# Migration: Phase 4 resilience — retry_count, idempotency_key, retrying status

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0015_contact_request_tenant_upload_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboundmessagequeue",
            name="retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="outboundmessagequeue",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="outboundmessagequeue",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("retrying", "Retrying"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
