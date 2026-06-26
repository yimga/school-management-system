# RLS enable for tenant-scoped marketplace tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['marketplace_appauditlog', 'marketplace_appbillingledger', 'marketplace_appinstallation', 'marketplace_apprating', 'marketplace_marketplacemonetizationledgerentry', 'marketplace_platformmarketplaceearning', 'marketplace_tenantmarketplacesubscription', 'marketplace_webhookdelivery']


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
        ("marketplace", "0013_developer_platform_v2"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
