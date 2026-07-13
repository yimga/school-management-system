"""Re-heal people ``school`` FK columns on tenant schemas that drifted.

Companion to academics 0057/0064 for the same "recorded-applied but column never
landed" django-tenants drift (see apps/tenancy/schema_repair.py). As a fresh graph
leaf this re-adds any missing people ``school`` FK columns on EVERY tenant schema
at the next ``migrate_schemas --tenant`` — a no-op where they already exist. Pure
RunPython (no model-state change), so ``makemigrations --check`` stays clean.
"""

from django.db import migrations


def _heal(apps, schema_editor):
    from apps.tenancy.schema_repair import ensure_app_school_id_columns

    ensure_app_school_id_columns("people")


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0066_transfercase_batch_status_index"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_heal, migrations.RunPython.noop),
    ]
