# Generated for metric 14 — inventory reorder-alert fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schoolops', '0033_inventory_movement_rls'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventoryitem',
            name='reorder_threshold',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Low-stock reorder level; an alert fires when quantity '
                'falls to or below this. 0 disables the alert for this item.',
            ),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='last_low_stock_notified_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Set when a low-stock alert was sent for the current '
                'low-stock episode; cleared when stock is replenished above the '
                'reorder level. Guarantees the alert fires once per episode.',
            ),
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='low_stock_notification_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
