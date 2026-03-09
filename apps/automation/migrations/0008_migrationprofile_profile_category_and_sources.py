# Migration Cloud: profile_category + FACTS, Skyward, Alma, SQL_DUMP, API_SIS

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0007_migrationprofile_source_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationprofile",
            name="profile_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("vendor", "Vendor"),
                    ("institution_type", "Institution type"),
                    ("geography", "Geography"),
                    ("data_condition", "Data condition"),
                    ("strategy", "Strategy"),
                ],
                db_index=True,
                help_text="Category for registry filtering: vendor, institution_type, geography, data_condition, strategy.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="migrationprofile",
            name="source_system",
            field=models.CharField(
                blank=True,
                choices=[
                    ("powerschool", "PowerSchool"),
                    ("blackbaud", "Blackbaud"),
                    ("veracross", "Veracross"),
                    ("infinite_campus", "Infinite Campus"),
                    ("facts", "FACTS"),
                    ("skyward", "Skyward"),
                    ("alma", "Alma"),
                    ("sql_dump", "SQL export"),
                    ("api_sis", "API SIS"),
                    ("other", "Other"),
                ],
                db_index=True,
                help_text="Prebuilt adapter for this SIS; null/other = generic.",
                max_length=32,
                null=True,
            ),
        ),
    ]
