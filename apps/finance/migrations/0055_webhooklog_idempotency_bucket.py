# Generated manually for payment webhook Idempotency-Key dedup (batch 15 #143).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0054_alter_paymentreminder_reminder_channels_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhooklog",
            name="idempotency_bucket",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Dedup key: transaction reference_id, or idempotency:<header> when Idempotency-Key is sent.",
                max_length=200,
            ),
        ),
    ]
