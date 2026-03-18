# World Engine Phase 2: JIT impersonation consent fields on School.
# Idempotent so tenant schemas that already have these columns do not fail.

import django.db.models.deletion
from django.conf import settings
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


def add_jit_fields_if_missing(apps, schema_editor):
    # Use AUTH_USER_MODEL table name (e.g. accounts_user), not auth_user
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    user_table = User._meta.db_table
    conn = schema_editor.connection
    table = "schools_school"
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            if not _column_exists_pg(cursor, table, "impersonation_consent_granted_at"):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN impersonation_consent_granted_at timestamp with time zone NULL"
                )
            if not _column_exists_pg(
                cursor, table, "impersonation_consent_granted_by_id"
            ):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN impersonation_consent_granted_by_id integer NULL"
                )
                cursor.execute(
                    """
                    DO $$ BEGIN
                      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'schools_school_impersonation_consent_granted_by_id_fkey') THEN
                        ALTER TABLE schools_school ADD CONSTRAINT schools_school_impersonation_consent_granted_by_id_fkey
                        FOREIGN KEY (impersonation_consent_granted_by_id) REFERENCES """
                    + user_table
                    + """(id) ON DELETE SET NULL;
                      END IF;
                    END $$
                    """
                )
        else:
            if not _column_exists_sqlite(
                cursor, table, "impersonation_consent_granted_at"
            ):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN impersonation_consent_granted_at datetime NULL"
                )
            if not _column_exists_sqlite(
                cursor, table, "impersonation_consent_granted_by_id"
            ):
                cursor.execute(
                    "ALTER TABLE schools_school ADD COLUMN impersonation_consent_granted_by_id integer NULL REFERENCES %s(id) ON DELETE SET NULL"
                    % user_table
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0023_world_engine"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="school",
                    name="impersonation_consent_granted_at",
                    field=models.DateTimeField(
                        blank=True,
                        help_text="When set, principal/school admin has consented to RunMyCampus support impersonation (JIT).",
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="school",
                    name="impersonation_consent_granted_by",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="User (e.g. principal) who granted impersonation consent.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_jit_fields_if_missing, noop),
            ],
        ),
    ]
