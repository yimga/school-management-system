from django.db import migrations


def _ensure_tables(apps, schema_editor):
    # Best-effort heal for tenant schemas missing PayrollOfflineCaptureRecord whose
    # CreateModel is recorded-applied but absent (fake-applied drift). New leaf →
    # no-op for merely-behind tenants; never aborts the deploy (guard savepoints).
    from apps.schools.tenant_schema_guard import ensure_models_tables

    ensure_models_tables(
        schema_editor, [apps.get_model("payroll", "PayrollOfflineCaptureRecord")]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0007_workforce_offline_capture_1511"),
    ]

    operations = [
        migrations.RunPython(_ensure_tables, migrations.RunPython.noop),
    ]
