"""
Seed DashboardPack + one default DashboardTemplate per pack so dashboard-pack
assignment works in every environment without an env flag (Dashboard Packs revival,
Phase 1). Idempotent: update_or_create by code / (pack, name). Reversible to a no-op.

Data comes from the model-free catalog module; rows are written via the historical
model (apps.get_model) per scan_migration_model_imports.
"""

from django.db import migrations

from apps.siteconfig.dashboard_pack_catalog import (
    DASHBOARD_PACKS,
    dashboard_template_for_pack,
    recommended_sectors_for,
)


def seed_packs(apps, schema_editor):
    DashboardPack = apps.get_model("siteconfig", "DashboardPack")
    DashboardTemplate = apps.get_model("siteconfig", "DashboardTemplate")

    for row in DASHBOARD_PACKS:
        family = row.get("family", "")
        pack, _ = DashboardPack.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "family": family,
                "description": row.get("description", ""),
                "version": "1.0",
                "is_active": True,
                "recommended_sectors": recommended_sectors_for(row),
            },
        )
        template_name, config_schema = dashboard_template_for_pack(row)
        DashboardTemplate.objects.update_or_create(
            dashboard_pack=pack,
            name=template_name,
            defaults={
                "description": row.get("description", ""),
                "config_schema": config_schema,
                "is_active": True,
            },
        )


def noop_reverse(apps, schema_editor):
    # Leave seeded catalog rows in place on reverse (assignments PROTECT them).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0197_dashboard_user_pref_role_packs"),
    ]

    operations = [
        migrations.RunPython(seed_packs, noop_reverse),
    ]
