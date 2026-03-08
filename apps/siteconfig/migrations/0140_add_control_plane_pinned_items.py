# Phase 8: Control plane Quick access (pinned sidebar items)
# Idempotent: (1) pre-check column existence; (2) ALTER inside savepoint; (3) on "already exists" rollback only savepoint.
# Safe for re-run on shared schema and any tenant schema.

from django.db import connection, migrations, models
from django.db.utils import OperationalError


def _column_exists_pg(cursor):
    """Return True if control_plane_pinned_items exists on siteconfig_dashboarduserpreference in current schema."""
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'siteconfig_dashboarduserpreference'
          AND column_name = 'control_plane_pinned_items'
        LIMIT 1
        """
    )
    return cursor.fetchone() is not None


def _is_duplicate_column_error(e):
    """True if exception indicates column already exists."""
    msg = str(e).lower()
    return "already exists" in msg or "duplicatecolumn" in msg or "duplicate column" in msg


def add_control_plane_pinned_items_if_missing(apps, schema_editor):
    """Add column; no-op if it already exists (safe for re-run on shared or tenant schemas)."""
    conn = schema_editor.connection
    vendor = conn.vendor
    if vendor == "postgresql":
        with conn.cursor() as cursor:
            if _column_exists_pg(cursor):
                return
        sid = connection.savepoint()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE siteconfig_dashboarduserpreference
                    ADD COLUMN control_plane_pinned_items JSONB NOT NULL DEFAULT '[]'::jsonb
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
            cursor.execute("PRAGMA table_info(siteconfig_dashboarduserpreference)")
            if any(row[1] == "control_plane_pinned_items" for row in cursor.fetchall()):
                return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE siteconfig_dashboarduserpreference
                    ADD COLUMN control_plane_pinned_items TEXT NOT NULL DEFAULT '[]'
                    """
                )
        except OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0139_phase4_workflow_dashboard_packs"),
    ]

    operations = [
        migrations.RunPython(add_control_plane_pinned_items_if_missing, noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="dashboarduserpreference",
                    name="control_plane_pinned_items",
                    field=models.JSONField(blank=True, default=list, help_text="Control plane sidebar item IDs to show in Quick access."),
                ),
            ],
            database_operations=[],  # already applied above
        ),
    ]
