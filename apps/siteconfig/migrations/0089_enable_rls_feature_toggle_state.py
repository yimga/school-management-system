# RLS for tenant-scoped FeatureToggleState rows. PostgreSQL only; no-op for SQLite/MySQL or schema-per-tenant.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls


POLICY_NAME = "siteconfig_featuretogglestate_tenant_isolation"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE siteconfig_featuretogglestate ENABLE ROW LEVEL SECURITY;"
        )
        cursor.execute(
            f"DROP POLICY IF EXISTS {POLICY_NAME} ON siteconfig_featuretogglestate;"
        )
        cursor.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON siteconfig_featuretogglestate
            FOR ALL
            USING (
                current_setting('app.current_school_id', true) IS NULL
                OR school_id IS NULL
                OR school_id::text = current_setting('app.current_school_id', true)
            )
            WITH CHECK (
                current_setting('app.current_school_id', true) IS NULL
                OR school_id IS NULL
                OR school_id::text = current_setting('app.current_school_id', true)
            );
            """
        )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP POLICY IF EXISTS {POLICY_NAME} ON siteconfig_featuretogglestate;"
        )
        cursor.execute(
            "ALTER TABLE siteconfig_featuretogglestate DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0088_featuretoggledefinition_featuretogglestate_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
