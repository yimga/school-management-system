# Generated manually for admission number configuration
# Date: 2026-01-28

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0042_sitesettings_grade_approval_auto_validate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="admission_number_mode",
            field=models.CharField(
                choices=[
                    ("AUTO", "Auto-generate (recommended)"),
                    ("MANUAL", "Manual entry only"),
                    ("AUTO_OR_MANUAL", "Allow auto or manual"),
                ],
                default="AUTO_OR_MANUAL",
                help_text=(
                    "Controls whether student admission numbers are auto-generated, "
                    "entered manually, or can be either. In AUTO/AUTO_OR_MANUAL modes, "
                    "leaving the field blank will generate a number using the school code."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="admission_number_pattern",
            field=models.CharField(
                blank=True,
                default=(
                    r"(\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4})|"
                    r"(\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4})"
                ),
                help_text=(
                    "Regex used to validate admission numbers. "
                    "Defaults to YY + SCHOOL + #### + SPEC + CLASS (no dashes) "
                    "or the legacy dashed format."
                ),
                max_length=255,
            ),
        ),
    ]
