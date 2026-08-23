# RLS enable + tenant policy for the migration_cloud tables scoped by a FK NAMED
# ``tenant`` / ``tenant_scope`` rather than ``school``.
#
# 0030/0031 and 0037/0038 sealed the tables whose FK is literally called
# ``school``. Eight tenant-scoped tables were left out — not by a judgement call
# but because every RLS gate we own decides "is this tenant-scoped?" by the FIELD
# NAME (scripts/scan_rls_table_coverage.py: `if "school" not in field_names:
# continue`). These eight carry the most sensitive material in the app:
# encrypted Companion bundle blobs and their receipts, the Companion keypairs,
# signed MAA agreements, webhook subscriptions (HMAC secrets), guardian consent
# tokens, intake requests, and tenant-scoped API tokens. Under
# USE_DJANGO_TENANTS=0 on PostgreSQL — the sovereign-edge mode where RLS *is*
# the isolation — they had none at all.
#
# Column names differ per table, so the policy is built per table instead of
# sharing one USING clause (0031's is hard-coded to ``school_id``).
#
# ``migration_cloud_migrationcloudapitoken`` additionally allows NULL scope
# through: ``tenant_scope`` is nullable and NULL means a PLATFORM-WIDE token.
# Bearer authentication resolves the token BEFORE any tenant is known, so a
# policy that hid NULL-scope rows would break operator API auth outright.
#
# NO FORCE here, deliberately — and unlike 0038 this is not a convention note,
# it is a verified constraint. Cross-tenant sweeps read these tables with no
# school GUC set and without ``rls_bypass()``: tasks_retention.py:78
# (CompanionCiphertextBlob), tasks_alerts.py:53 (MigrationCloudAPIToken),
# purge_completed_migration_bundles.py:297, maa_v2_resign_campaign.py:160. With
# FORCE, the owner role stops bypassing and each of those silently reads zero
# rows — retention and expiry alarms would go quiet rather than fail loudly.
# FORCE belongs in a follow-up that first wraps those four call sites in
# ``apps.schools.rls_context.rls_bypass()``.
#
# No-op on SQLite and when USE_DJANGO_TENANTS=True (schema mode).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

#: The sealed tables. A FLAT LIST OF LITERALS under the name ``TABLES`` on
#: purpose — every RLS coverage scanner reads this file with ``ast`` and only
#: sees string constants, so a comprehension or a list of tuples here would
#: leave the tables looking uncovered no matter what this migration executes.
TABLES = [
    "migration_cloud_companionciphertextblob",
    "migration_cloud_companionuploadreceipt",
    "migration_cloud_migrationauthorizationagreement",
    "migration_cloud_migrationcloudcompanionkeypair",
    "migration_cloud_migrationcloudwebhooksubscription",
    "migration_cloud_migrationintakerequest",
    "migration_cloud_guardianconsenttoken",
    "migration_cloud_migrationcloudapitoken",
]

#: db_table → the column carrying the School FK (they are not all ``school_id``).
TENANT_COLUMN = {
    "migration_cloud_companionciphertextblob": "tenant_id",
    "migration_cloud_companionuploadreceipt": "tenant_id",
    "migration_cloud_migrationauthorizationagreement": "tenant_id",
    "migration_cloud_migrationcloudcompanionkeypair": "tenant_id",
    "migration_cloud_migrationcloudwebhooksubscription": "tenant_id",
    "migration_cloud_migrationintakerequest": "tenant_id",
    "migration_cloud_guardianconsenttoken": "tenant_id",
    "migration_cloud_migrationcloudapitoken": "tenant_scope_id",
}

#: Tables whose tenant column is NULLABLE and where NULL means platform-wide.
NULL_SCOPE_IS_PLATFORM_WIDE = {"migration_cloud_migrationcloudapitoken"}


def _using_clause(column: str, allow_null: bool) -> str:
    null_arm = f"\n        OR {column} IS NULL" if allow_null else ""
    return f"""(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND {column}::text = current_setting('app.current_school_id', true)
    ){null_arm}
)"""


def _policy_name(table: str) -> str:
    short = table.replace("migration_cloud_", "", 1)
    return f"migration_cloud_tenant_{short}"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            policy_name = _policy_name(table)
            using = _using_clause(
                TENANT_COLUMN[table], table in NULL_SCOPE_IS_PLATFORM_WIDE
            )
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {using}
                WITH CHECK {using};
                """
            )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy_name = _policy_name(table)
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0045_onboarding_waiver_audit_event_types"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
