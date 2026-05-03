# Operator DLQ disposition on platform webhook deliveries

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("platform_runtime", "0056_align_event_webhook_schema"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventwebhookdelivery",
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
            model_name="eventwebhookdelivery",
            name="operator_resolution_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="eventwebhookdelivery",
            name="operator_resolution_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventwebhookdelivery",
            name="operator_resolution_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
