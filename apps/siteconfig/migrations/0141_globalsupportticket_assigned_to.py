# Support queue refinement: assignment (SCOPED_WORK_VERIFICATION §2)
# Idempotent: (1) pre-check column existence; (2) ALTER inside savepoint; (3) on "already exists" rollback savepoint only.

from django.conf import settings
from django.db import connection, migrations, models


def _column_exists_pg(cursor, table, column):
    """Return True if column exists on table in current schema."""
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        LIMIT 1
        """,
        [table, column],
    )
    return cursor.fetchone() is not None


def _is_duplicate_column_error(e):
    msg = str(e).lower()
    return "already exists" in msg or "duplicatecolumn" in msg or "duplicate column" in msg


def add_assigned_to_if_missing(apps, schema_editor):
    """Add assigned_to_id column; no-op if it already exists."""
    conn = schema_editor.connection
    vendor = conn.vendor
    if vendor == "postgresql":
        with conn.cursor() as cursor:
            if _column_exists_pg(cursor, "siteconfig_globalsupportticket", "assigned_to_id"):
                return
        sid = connection.savepoint()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE siteconfig_globalsupportticket
                    ADD COLUMN assigned_to_id integer NULL
                    REFERENCES auth_user(id) ON DELETE SET NULL
                    """
                )
        except Exception as e:
            if _is_duplicate_column_error(e):
                connection.savepoint_rollback(sid)
            else:
                raise
        else:
            connection.savepoint_commit(sid)
    elif vendor == "sqlite":
        with conn.cursor() as cursor:
            cursor.execute("PRAGMA table_info(siteconfig_globalsupportticket)")
            if any(row[1] == "assigned_to_id" for row in cursor.fetchall()):
                return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE siteconfig_globalsupportticket
                    ADD COLUMN assigned_to_id integer NULL
                    """
                )
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                raise


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0140_add_control_plane_pinned_items"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(add_assigned_to_if_missing, noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="globalsupportticket",
                    name="assigned_to",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Super-admin or support agent assigned to this ticket.",
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="assigned_support_tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
