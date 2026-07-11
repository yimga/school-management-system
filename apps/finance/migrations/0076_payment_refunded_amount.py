from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0075_fractionalpaymentledger"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="refunded_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Cumulative amount refunded against this payment. Net money "
                    "received is amount - refunded_amount; a full refund also "
                    "flips status to 'refunded'. Written only by "
                    "services.process_refund_request."
                ),
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
