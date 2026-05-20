# Generated for global weather location catalog persistence.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0179_regionconfig_week_start_day"),
    ]

    operations = [
        migrations.AddField(
            model_name="weatherlocation",
            name="catalog_source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Stable geonames (or catalog) identifier for API lookups.",
                max_length=32,
                null=True,
                unique=True,
            ),
        ),
    ]
