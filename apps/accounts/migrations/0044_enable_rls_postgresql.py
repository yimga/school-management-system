# RLS enable for tenant-scoped accounts tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['accounts_accessrole', 'accounts_device_registration', 'accounts_offline_access_intent', 'accounts_offline_capability_token', 'accounts_relationship_tuple', 'accounts_securityauditlog', 'accounts_tenantstaffinvite', 'accounts_usertenantbinding']


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
        ("accounts", "0043_securityauditlog_ownership_changed_event"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
