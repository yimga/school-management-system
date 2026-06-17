from django.db import migrations


def _ensure_tables(apps, schema_editor):
    # Best-effort heal for tenant schemas missing the finance offline-capture
    # tables whose CreateModel is recorded-applied but absent (fake-applied drift).
    # New leaf → no-op for merely-behind tenants (CreateModel already ran); never
    # aborts the deploy (per-model savepoint + log-and-skip in the guard).
    from apps.schools.tenant_schema_guard import ensure_models_tables

    models = [
        apps.get_model("finance", "OfflinePaymentIntent"),
        apps.get_model("finance", "FinanceOfflineCaptureRecord"),
    ]
    ensure_models_tables(schema_editor, models)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0067_notification_unread_dedup_constraint"),
    ]

    operations = [
        migrations.RunPython(_ensure_tables, migrations.RunPython.noop),
    ]
