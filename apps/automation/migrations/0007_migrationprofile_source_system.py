# Migration Cloud Phase A: competitor adapters

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0006_add_migration_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationprofile",
            name="source_system",
            field=models.CharField(
                blank=True,
                choices=[
                    ("powerschool", "PowerSchool"),
                    ("blackbaud", "Blackbaud"),
                    ("veracross", "Veracross"),
                    ("infinite_campus", "Infinite Campus"),
                    ("other", "Other"),
                ],
                db_index=True,
                help_text="Prebuilt adapter for this SIS; null/other = generic.",
                max_length=32,
                null=True,
            ),
        ),
    ]
