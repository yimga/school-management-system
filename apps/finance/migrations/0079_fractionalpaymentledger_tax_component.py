from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0078_payment_currency_code_resolved_not_usd"),
    ]

    operations = [
        migrations.AddField(
            model_name="fractionalpaymentledger",
            name="tax_component",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Portion of `amount` attributable to tax, snapshotted at post "
                    "time by proportional allocation (amount x invoice-tax-fraction). "
                    "Enables cash-basis VAT-collected remittance reporting from "
                    "irregular partial posts. Purely informational: never affects "
                    "amount / running / balance."
                ),
                max_digits=12,
            ),
        ),
    ]
