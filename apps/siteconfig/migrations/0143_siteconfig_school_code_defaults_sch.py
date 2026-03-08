from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0142_sitesettings_sms_sender_id_runmycampus"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="school_code",
            field=models.CharField(
                default="SCH",
                help_text="Short code used in admission numbers (e.g., SCH).",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="tenantadmissionnumberpolicy",
            name="school_code",
            field=models.CharField(default="SCH", max_length=20),
        ),
    ]
