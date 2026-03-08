# Phase 8: Control plane Quick access (pinned sidebar items)
# Idempotent: skip adding column if it already exists (e.g. tenant schema partially migrated).

from django.db import migrations, models


def add_control_plane_pinned_items_if_missing(apps, schema_editor):
    """Add column only if it does not exist (safe for re-run on tenant schemas)."""
    conn = schema_editor.connection
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'siteconfig_dashboarduserpreference'
                  AND column_name = 'control_plane_pinned_items'
                LIMIT 1
                """
            )
            if cursor.fetchone() is not None:
                return
            cursor.execute(
                """
                ALTER TABLE siteconfig_dashboarduserpreference
                ADD COLUMN control_plane_pinned_items JSONB NOT NULL DEFAULT '[]'::jsonb
                """
            )
        elif vendor == "sqlite":
            cursor.execute("PRAGMA table_info(siteconfig_dashboarduserpreference)")
            if any(row[1] == "control_plane_pinned_items" for row in cursor.fetchall()):
                return
            cursor.execute(
                """
                ALTER TABLE siteconfig_dashboarduserpreference
                ADD COLUMN control_plane_pinned_items TEXT NOT NULL DEFAULT '[]'
                """
            )


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
