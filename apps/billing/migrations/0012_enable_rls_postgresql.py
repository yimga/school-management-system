# RLS enable for tenant-scoped billing tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['billing_billingaccount', 'billing_billingprocessorsyncevent', 'billing_entitlement', 'billing_platformledgerentry', 'billing_quote', 'billing_tenantsubscription', 'billing_usagecap', 'billing_usagemeter']


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0011_billingaccount_parent_account"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
