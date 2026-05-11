"""Expand StudentProfile.gender choices to include NON_BINARY and PREFER_NOT_TO_SAY.

UK/EU/Canadian/Australian school authorities increasingly require non-binary recording
and an explicit "prefer not to say" option separate from blank. Existing rows are
untouched; this migration only extends the available choices.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0044_student_passport_membership_vault_slice13"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentprofile",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MALE", "Male"),
                    ("FEMALE", "Female"),
                    ("NON_BINARY", "Non-binary"),
                    ("OTHER", "Other"),
                    ("PREFER_NOT_TO_SAY", "Prefer not to say"),
                ],
                max_length=20,
            ),
        ),
    ]
