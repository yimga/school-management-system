# Add school_type to School (module manifest). Idempotent for Render tenant schemas.

from django.db import migrations, models


def _column_exists_pg(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        [table, column],
    )
    return cursor.fetchone() is not None


def _column_exists_sqlite(cursor, table, column):
    cursor.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cursor.fetchall())


def add_school_type_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    table = "schools_school"
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            if not _column_exists_pg(cursor, table, "school_type"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN school_type varchar(32) NOT NULL DEFAULT 'BASE_SCHOOL'"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS schools_school_school_type_idx ON schools_school (school_type)"
                )
        else:
            if not _column_exists_sqlite(cursor, table, "school_type"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN school_type varchar(32) NOT NULL DEFAULT 'BASE_SCHOOL'"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS schools_school_school_type_idx ON schools_school (school_type)"
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0024_world_engine_phase2"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="school",
                    name="school_type",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="BASE_SCHOOL",
                        help_text="School type from module manifest (BASE_SCHOOL, TECHNICAL_COLLEGE, STEM_ACADEMY). Determines required_apps and UI skin.",
                        max_length=32,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_school_type_if_missing, noop),
            ],
        ),
    ]
