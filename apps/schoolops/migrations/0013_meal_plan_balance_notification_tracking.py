# v3.32.0 — MealPlanBalance low-balance notification tracking.
#
# Pure AddField — no live-model imports (scan_migration_model_imports
# zero-tolerance gate). Adds two fields used by the signal +
# Celery-task low-balance notification flow in Agent 4 wave.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0012_assignment_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="mealplanbalance",
            name="last_low_balance_notification_sent_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Timestamp of the most recent low-balance notification "
                    "delivery; used by the cooldown gate."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mealplanbalance",
            name="low_balance_notification_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Lifetime count of low-balance notifications dispatched "
                    "for this row (analytics + spam-detection)."
                ),
            ),
        ),
    ]
