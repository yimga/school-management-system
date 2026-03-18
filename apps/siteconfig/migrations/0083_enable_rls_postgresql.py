# RLS (Row-Level Security) for tenant-scoped OfficialReportTemplate. PostgreSQL only; no-op for SQLite/MySQL or schema-per-tenant.

from django.db import migrations, connection

from apps.schools.rls import should_apply_rls


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE siteconfig_officialreporttemplate ENABLE ROW LEVEL SECURITY;"
        )
        cursor.execute("""
            CREATE POLICY siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate
            FOR ALL
            USING (
                current_setting('app.current_school_id', true) IS NULL
                OR school_id::text = current_setting('app.current_school_id', true)
            )
            WITH CHECK (
                current_setting('app.current_school_id', true) IS NULL
                OR school_id::text = current_setting('app.current_school_id', true)
            );
        """)


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS siteconfig_officialreporttemplate_tenant_isolation ON siteconfig_officialreporttemplate;"
        )
        cursor.execute(
            "ALTER TABLE siteconfig_officialreporttemplate DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0082_add_official_report_template"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
