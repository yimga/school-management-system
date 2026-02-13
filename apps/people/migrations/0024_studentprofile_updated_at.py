# Migration from main branch: add updated_at to StudentProfile for audit/tracking.
# Kept so migration graph can merge with 0024_add_school_fk (multi-tenant) branch.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0023_add_badge_scan_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
