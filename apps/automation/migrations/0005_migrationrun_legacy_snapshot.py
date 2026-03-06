# Section 11.1: Read-only legacy view — store uploaded rows for display

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0004_migrationrun_rollback_snapshot_rolled_back"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationrun",
            name="legacy_snapshot",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Read-only copy of uploaded rows for legacy view (no PII in logs).",
            ),
        ),
    ]
