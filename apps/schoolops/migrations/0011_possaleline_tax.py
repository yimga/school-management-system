# POS: optional sales tax / VAT snapshot per line (Wave 4 retail depth increment).

from decimal import Decimal

from django.db import migrations, models


def forwards_zero_tax(apps, schema_editor):
    PosSaleLine = apps.get_model("schoolops", "PosSaleLine")
    PosSaleLine.objects.all().update(
        tax_rate_percent=Decimal("0"),
        tax_amount=Decimal("0"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0010_possaleline_inventory_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="possaleline",
            name="tax_rate_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Sales tax / VAT rate snapshot for this line (0–100).",
                max_digits=5,
            ),
        ),
        migrations.AddField(
            model_name="possaleline",
            name="tax_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Tax amount charged on this line at sale time.",
                max_digits=12,
            ),
        ),
        migrations.RunPython(forwards_zero_tax, migrations.RunPython.noop),
    ]
