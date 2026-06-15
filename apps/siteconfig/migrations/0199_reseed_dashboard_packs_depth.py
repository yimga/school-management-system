"""
Re-seed dashboard packs with depth (Dashboard Packs revival — depth + breadth).

0198 already created packs/templates; this re-runs the idempotent upsert so every
existing template gets the richer config_schema (modules / kpis / theme that actually
drive what renders) and the new breadth packs (e.g. extra student packs) are added.
Idempotent; reverse is a no-op. Data via the model-free catalog + apps.get_model.
"""

from django.db import migrations

from apps.siteconfig.dashboard_pack_catalog import apply_seed


def reseed(apps, schema_editor):
    apply_seed(
        apps.get_model("siteconfig", "DashboardPack"),
        apps.get_model("siteconfig", "DashboardTemplate"),
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0198_seed_dashboard_packs_templates"),
    ]

    operations = [
        migrations.RunPython(reseed, noop_reverse),
    ]
