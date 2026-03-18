# Generated migration to add status field to Payment model
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0016_add_payment_proof_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="status",
            field=models.CharField(default="pending", max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="payment",
            name="status_reason",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
    ]
