# Payment idempotency: unique (invoice, external_reference) when ext ref present

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0062_bankaccountchangerequest"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_reference", ""), _negated=True),
                fields=("invoice", "external_reference"),
                name="finance_payment_uniq_invoice_ext_ref",
            ),
        ),
    ]
