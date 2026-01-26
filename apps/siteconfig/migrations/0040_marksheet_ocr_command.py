from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0039_report_preview_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="marksheet_ocr_command",
            field=models.CharField(
                help_text="Absolute path to the Tesseract binary when the executable is not on PATH.",
                max_length=255,
                blank=True,
                default="",
            ),
        ),
    ]
