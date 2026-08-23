# RLS enable + hybrid policy for FeaturePermissionScope (nullable school FK).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ["accounts_featurepermissionscope"]

HYBRID_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR school_id IS NULL
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


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


def apply_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy_name = "accounts_tenant_featurepermissionscope"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {HYBRID_CLAUSE}
                WITH CHECK {HYBRID_CLAUSE};
                """
            )


def reverse_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy_name = "accounts_tenant_featurepermissionscope"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0061_feature_permission_school_scope"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
        migrations.RunPython(apply_policy, reverse_policy),
    ]
