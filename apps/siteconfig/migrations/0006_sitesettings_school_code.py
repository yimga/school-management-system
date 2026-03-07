from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0005_sitesettings_company_address_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="school_code",
            field=models.CharField(
                default="GIL",
                help_text="Short code used in admission numbers (e.g., GIL).",
                max_length=20,
            ),
        ),
    ]
