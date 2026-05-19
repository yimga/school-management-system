# Generated manually for five-pillar Shopify gear-up (race-safe webhook dedup).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0063_payment_uniq_invoice_ext_ref"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="webhooklog",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_bucket", ""), _negated=True),
                fields=("provider", "idempotency_bucket"),
                name="finance_webhooklog_uniq_provider_bucket",
            ),
        ),
    ]
