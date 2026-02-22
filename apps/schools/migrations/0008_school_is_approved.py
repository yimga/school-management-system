# Phase H: Optional approval workflow — is_approved on School

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0007_school_theme_choice"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="is_approved",
            field=models.BooleanField(
                default=True,
                help_text="When False, school is pending approval (e.g. Super Admin queue). Default True for backward compatibility.",
            ),
        ),
    ]
