# Generated manually for Phase 3 BadgeType enrichment

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0021_add_badge_and_badge_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="badgetype",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="badgetype",
            name="icon",
            field=models.CharField(
                blank=True,
                help_text="Icon name/code (e.g. Bootstrap icon class).",
                max_length=60,
            ),
        ),
        migrations.AddField(
            model_name="badgetype",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="badgetype",
            options={
                "ordering": ["audience", "sort_order", "code"],
                "verbose_name": "Badge type",
                "verbose_name_plural": "Badge types",
            },
        ),
    ]
