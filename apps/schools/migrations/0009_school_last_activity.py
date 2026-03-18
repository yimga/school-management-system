# Phase H optional: tenant health — last_activity on School

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0008_school_is_approved"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="last_activity",
            field=models.DateTimeField(
                blank=True,
                help_text="Phase H optional: last request time for this tenant (throttled updates).",
                null=True,
            ),
        ),
    ]
