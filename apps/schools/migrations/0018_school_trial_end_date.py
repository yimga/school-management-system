# Plan X: Trial state — trial_end_date on School

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0017_add_hierarchy_campus_quota_usage"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="trial_end_date",
            field=models.DateField(
                null=True,
                blank=True,
                help_text="When billing_type is FREE_TRIAL, trial ends on this date.",
            ),
        ),
    ]
