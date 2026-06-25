# Generated for batch 1740 — discipline MTSS + parent notification timestamp

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0058_remove_term_term_position_range_1_4_or_null_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="mtss_tier",
            field=models.CharField(
                blank=True,
                choices=[("1", "Tier 1 — Universal"), ("2", "Tier 2 — Targeted"), ("3", "Tier 3 — Intensive")],
                default="1",
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="incident",
            name="parent_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
