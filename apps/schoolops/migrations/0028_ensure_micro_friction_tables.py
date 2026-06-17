from django.db import migrations


def _ensure_tables(apps, schema_editor):
    # Best-effort heal for tenant schemas missing the schoolops micro-friction
    # offline tables whose CreateModel (0018) is recorded-applied but absent
    # (fake-applied drift). New leaf → no-op for merely-behind tenants; never
    # aborts the deploy (per-model savepoint + log-and-skip in the guard).
    from apps.schools.tenant_schema_guard import ensure_models_tables

    models = [
        apps.get_model("schoolops", "SubstituteHandoverPacketRecord"),
        apps.get_model("schoolops", "LostBelongingsTagRecord"),
        apps.get_model("schoolops", "LostBelongingsCustodyEventRecord"),
    ]
    ensure_models_tables(schema_editor, models)


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0027_ensure_visitorcheckin_offline_id"),
    ]

    operations = [
        migrations.RunPython(_ensure_tables, migrations.RunPython.noop),
    ]
