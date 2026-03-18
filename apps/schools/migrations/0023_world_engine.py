# World Engine: add branding_metadata, dedicated_db_alias, regional_cluster to School.
# Idempotent so tenant schemas that already have these columns (e.g. from a prior deploy) do not fail.

from django.db import migrations, models


def _column_exists_sqlite(cursor, table, column):
    cursor.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cursor.fetchall())


def add_school_fields_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        table = "schools_school"
        if conn.vendor == "postgresql":

            def col_exists(name):
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    [table, name],
                )
                return cursor.fetchone() is not None

            if not col_exists("branding_metadata"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN branding_metadata jsonb NOT NULL DEFAULT '{}'"
                )
            if not col_exists("dedicated_db_alias"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN dedicated_db_alias varchar(63) NOT NULL DEFAULT ''"
                )
            if not col_exists("regional_cluster"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN regional_cluster varchar(63) NOT NULL DEFAULT ''"
                )
        else:
            # SQLite (local/CI)
            if not _column_exists_sqlite(cursor, table, "branding_metadata"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN branding_metadata text NOT NULL DEFAULT '{}'"
                )
            if not _column_exists_sqlite(cursor, table, "dedicated_db_alias"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN dedicated_db_alias varchar(63) NOT NULL DEFAULT ''"
                )
            if not _column_exists_sqlite(cursor, table, "regional_cluster"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN regional_cluster varchar(63) NOT NULL DEFAULT ''"
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0022_backfill_schooldomain"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="school",
                    name="branding_metadata",
                    field=models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Optional: {"primary": "#hex", "accent": "#hex", "font": "Family, sans-serif"}. Maps to --primary, --accent in tenant CSS.',
                    ),
                ),
                migrations.AddField(
                    model_name="school",
                    name="dedicated_db_alias",
                    field=models.CharField(
                        blank=True,
                        help_text="Optional: dedicated DB alias for mega-schools (10k+ students). Super Admin can set.",
                        max_length=63,
                    ),
                ),
                migrations.AddField(
                    model_name="school",
                    name="regional_cluster",
                    field=models.CharField(
                        blank=True,
                        help_text="Optional: region cluster for DB routing (e.g. eu, apac). Used with multi-DB router.",
                        max_length=63,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_school_fields_if_missing, noop),
            ],
        ),
    ]
