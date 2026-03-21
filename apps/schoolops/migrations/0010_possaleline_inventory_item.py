# Wave 19 — POS ↔ inventory link

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0009_possaleline"),
    ]

    operations = [
        migrations.AddField(
            model_name="possaleline",
            name="inventory_item",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional link to stock line when Inventory module is enabled.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pos_sale_lines",
                to="schoolops.inventoryitem",
            ),
        ),
    ]
