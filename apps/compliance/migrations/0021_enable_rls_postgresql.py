# RLS enable for tenant-scoped compliance tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['compliance_auditoraccessgrant', 'compliance_consentrecord', 'compliance_consentrequest', 'compliance_eraserequest', 'compliance_exportjob', 'compliance_ferpadisclosure', 'compliance_nonrepudiationlogentry', 'compliance_retentionrule']


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
        ("compliance", "0020_rename_compliance__model__797756_idx_compliance__model_l_c9c42b_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
