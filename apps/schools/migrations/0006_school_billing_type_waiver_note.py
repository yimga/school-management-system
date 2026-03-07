# Global Powerhouse Phase E: billing_type and waiver_note for SuperUser fee waiver

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0005_school_plan_and_addons"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="billing_type",
            field=models.CharField(
                choices=[
                    ("REGULAR", "Regular (paying)"),
                    ("FREE_TRIAL", "Free trial"),
                    ("COMPLIMENTARY", "Complimentary (waived)"),
                    ("MANUAL_OVERRIDE", "Manual override (full access)"),
                ],
                default="REGULAR",
                help_text="When COMPLIMENTARY or MANUAL_OVERRIDE, billing checks are skipped; waiver_note required.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="waiver_note",
            field=models.CharField(
                blank=True,
                help_text="Required when billing_type is COMPLIMENTARY or MANUAL_OVERRIDE (e.g. partnership with NGO).",
                max_length=500,
            ),
        ),
    ]
