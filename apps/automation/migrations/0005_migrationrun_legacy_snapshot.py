# Section 11.1: Read-only legacy view — store uploaded rows for display. Idempotent for tenant migrations.

from django.db import migrations, models


def add_legacy_snapshot_if_missing(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE automation_migrationrun ADD COLUMN legacy_snapshot jsonb NOT NULL DEFAULT '{}';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
        else:
            cursor.execute("PRAGMA table_info(automation_migrationrun)")
            if "legacy_snapshot" not in [row[1] for row in cursor.fetchall()]:
                cursor.execute("ALTER TABLE automation_migrationrun ADD COLUMN legacy_snapshot text NOT NULL DEFAULT '{}'")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0004_migrationrun_rollback_snapshot_rolled_back"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="migrationrun",
                    name="legacy_snapshot",
                    field=models.JSONField(
                        default=dict,
                        blank=True,
                        help_text="Read-only copy of uploaded rows for legacy view (no PII in logs).",
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(add_legacy_snapshot_if_missing, noop)],
        ),
    ]
