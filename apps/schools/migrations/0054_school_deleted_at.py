# Wave L4 (v3.61.3, 2026-05-22): reversible soft-delete on School.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0053_schoolprovisioningevent_offboarding_extended"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Soft-delete timestamp. NULL when school is live; set when offboarding requested.",
                null=True,
            ),
        ),
    ]
