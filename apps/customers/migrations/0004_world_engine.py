# World Engine: add db_alias to Client. Idempotent so tenant schemas that
# already have the column (e.g. from a prior deploy) do not fail.

from django.db import migrations, models


def add_db_alias_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor == "postgresql":
        with conn.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE customers_client
                ADD COLUMN IF NOT EXISTS db_alias varchar(63) NOT NULL DEFAULT ''
            """)
    else:
        with conn.cursor() as cursor:
            cursor.execute("PRAGMA table_info(customers_client)")
            cols = [row[1] for row in cursor.fetchall()]
            if "db_alias" not in cols:
                cursor.execute(
                    "ALTER TABLE customers_client ADD COLUMN db_alias varchar(63) NOT NULL DEFAULT ''"
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0003_ensure_gilead_tenant_domain"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="client",
                    name="db_alias",
                    field=models.CharField(
                        blank=True,
                        help_text="Optional: database alias for this tenant (e.g. region_eu, dedicated_xyz). Leave blank for default.",
                        max_length=63,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_db_alias_if_missing, noop),
            ],
        ),
    ]
