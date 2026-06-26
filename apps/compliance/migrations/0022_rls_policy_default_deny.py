# RLS default-deny for tenant-scoped compliance tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['compliance_auditoraccessgrant', 'compliance_consentrecord', 'compliance_consentrequest', 'compliance_eraserequest', 'compliance_exportjob', 'compliance_ferpadisclosure', 'compliance_nonrepudiationlogentry', 'compliance_retentionrule']
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("compliance_", "", 1)
            policy_name = f"compliance_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("compliance_", "", 1)
            policy_name = f"compliance_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0021_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
