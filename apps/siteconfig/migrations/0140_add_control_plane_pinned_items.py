# Phase 8: Control plane Quick access (pinned sidebar items)
# Idempotent: try ADD COLUMN and ignore "column already exists" (safe for re-run on tenant schemas).

from django.db import migrations, models
from django.db.utils import OperationalError, ProgrammingError


def add_control_plane_pinned_items_if_missing(apps, schema_editor):
    """Add column; no-op if it already exists (safe for re-run on tenant schemas)."""
    conn = schema_editor.connection
    vendor = conn.vendor
    if vendor == "postgresql":
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE siteconfig_dashboarduserpreference
                    ADD COLUMN control_plane_pinned_items JSONB NOT NULL DEFAULT '[]'::jsonb
                    """
                )
        except ProgrammingError as e:
            if "already exists" not in str(e):
                raise
    elif vendor == "sqlite":
        try:
            with conn.cursor() as cursor:
                cursor.execute("PRAGMA table_info(siteconfig_dashboarduserpreference)")
                if any(row[1] == "control_plane_pinned_items" for row in cursor.fetchall()):
                    return
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
