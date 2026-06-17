from django.db import migrations


def _ensure_tables(apps, schema_editor):
    # Best-effort heal for tenant schemas where StudentNote's CreateModel (0049)
    # is recorded-applied but the table is missing (fake-applied drift). New leaf
    # → runs AFTER 0049 under `migrate_schemas --tenant`, so a merely-behind tenant
    # has the table by now and this is a no-op. Never aborts the deploy (the guard
    # creates each table in its own savepoint and logs-and-skips on failure).
    from apps.schools.tenant_schema_guard import ensure_models_tables

    ensure_models_tables(schema_editor, [apps.get_model("people", "StudentNote")])


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0059_ensure_people_offline_sync_columns"),
    ]

    operations = [
        migrations.RunPython(_ensure_tables, migrations.RunPython.noop),
    ]
