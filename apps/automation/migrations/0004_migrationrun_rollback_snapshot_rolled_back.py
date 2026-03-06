# Migration: rollback support for MigrationRun (11.1, 29.6)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0003_migration_run"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationrun",
            name="rollback_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="migrationrun",
            name="rolled_back_by_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rollback_of_run",
                to="automation.migrationrun",
                help_text="When set, this run reverted the migration recorded by the linked run.",
            ),
        ),
    ]
