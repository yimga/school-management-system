# Allow multiple geonames rows per country when city names collide.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0180_weatherlocation_catalog_source_id"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="weatherlocation",
            unique_together=set(),
        ),
    ]
