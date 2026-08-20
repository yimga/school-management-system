# RLS ENABLE + FORCE + default-deny for lifecycle_edgeonboardingrun.
#
# 0006 created the table after lifecycle 0004/0005 already ran, so those
# frozen TABLES lists never cover it. Same class as schoolops/0038: ENABLE,
# CREATE POLICY, and FORCE in one pass (0083 cannot re-sweep this table).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "lifecycle_edgeonboardingrun",
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_policy_force(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("lifecycle_", "", 1)
            policy_name = f"lifecycle_tenant_{short}"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def reverse_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("lifecycle_", "", 1)
            policy_name = f"lifecycle_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("lifecycle", "0006_edgeonboardingrun"),
    ]

    operations = [
        migrations.RunPython(enable_policy_force, reverse_rls),
    ]
