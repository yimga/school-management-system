# Migration: rollback support for MigrationRun (11.1, 29.6). Idempotent for tenant migrations.

from django.db import migrations, models
import django.db.models.deletion


def add_columns_if_missing(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE automation_migrationrun ADD COLUMN rollback_snapshot jsonb NOT NULL DEFAULT '{}';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE automation_migrationrun ADD COLUMN rolled_back_by_run_id bigint NULL REFERENCES automation_migrationrun(id) ON DELETE SET NULL;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS automation_migrationrun_rolled_back_by_run_id_idx ON automation_migrationrun (rolled_back_by_run_id)")
        else:
            cursor.execute("PRAGMA table_info(automation_migrationrun)")
            cols = [row[1] for row in cursor.fetchall()]
            if "rollback_snapshot" not in cols:
                cursor.execute("ALTER TABLE automation_migrationrun ADD COLUMN rollback_snapshot text NOT NULL DEFAULT '{}'")
            if "rolled_back_by_run_id" not in cols:
                cursor.execute("ALTER TABLE automation_migrationrun ADD COLUMN rolled_back_by_run_id integer NULL REFERENCES automation_migrationrun(id) ON DELETE SET NULL")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0003_migration_run"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
            ],
            database_operations=[migrations.RunPython(add_columns_if_missing, noop)],
        ),
    ]
