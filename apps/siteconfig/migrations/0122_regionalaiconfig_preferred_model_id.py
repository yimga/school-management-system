# Add preferred_model_id to RegionalAIConfig. Idempotent for Render.

from django.db import migrations, models


def add_preferred_model_id_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    table = "siteconfig_regionalaiconfig"
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                [table, "preferred_model_id"],
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "ALTER TABLE siteconfig_regionalaiconfig ADD COLUMN preferred_model_id varchar(128) NOT NULL DEFAULT ''"
                )
        else:
            cursor.execute("PRAGMA table_info(%s)" % table)
            if not any(row[1] == "preferred_model_id" for row in cursor.fetchall()):
                cursor.execute(
                    "ALTER TABLE siteconfig_regionalaiconfig ADD COLUMN preferred_model_id varchar(128) NOT NULL DEFAULT ''"
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0121_add_ai_embedding_store"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="regionalaiconfig",
                    name="preferred_model_id",
                    field=models.CharField(
                        blank=True,
                        help_text="Optional override: when set, used instead of registry/default (Super Admin can flip without touching LB).",
                        max_length=128,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_preferred_model_id_if_missing, noop),
            ],
        ),
    ]
