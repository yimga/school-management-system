# RLS for the tenant-scoped table the rollout-ring wave adds.
#
# `scan_rls_table_coverage.py` is a ZERO-baseline gate: it asks whether THIS TABLE is
# named in some enable_rls migration, not whether the app has any. `EdgeRolloutPolicy`
# carries a `school` FK, so it is tenant-scoped and must be enumerated here or the gate
# goes red the moment this lands — which is exactly what happened to the pairing wave in
# PR #184, and why 0017 exists.
#
# `ManifestRelease` is deliberately ABSENT from this migration. It has no `school` FK
# because how far a release has been promoted is a property of the RELEASE and is
# identical for every school in the fleet; it is fleet state, not tenant data. Adding a
# school FK to make it "consistent" would both misdescribe it and enrol it in the tenant
# RLS gate for data it does not hold — the same call `EdgeDeploymentHistory` makes.
#
# SCOPE, stated so this is not over-read: `should_apply_rls` returns False under
# USE_DJANGO_TENANTS, which render.yaml sets, so this is a NO-OP in the deployed
# schema-per-tenant topology — isolation there is Postgres schemas plus service-layer
# `school=` scoping. What it buys is RLS-MODE READINESS for a deployment running with
# USE_DJANGO_TENANTS=0 on PostgreSQL, where RLS *is* the isolation.
#
# `school_id` is NOT NULL here (a OneToOneField to School), so the strict predicate
# applies with no unclaimed-row exception — unlike `EdgePairingRequest` in 0017, whose
# school is nullable by design.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "sync_engine_edgerolloutpolicy",
]

_TENANT_MATCH = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _policy_name(table: str) -> str:
    return f"sync_engine_tenant_{table.removeprefix('sync_engine_')}"


def apply_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy = _policy_name(table)
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            # FORCE, or the table-owner role (Django's own) bypasses the policy and the
            # whole thing is decorative.
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy} ON {table}
                FOR ALL
                USING {_TENANT_MATCH}
                WITH CHECK {_TENANT_MATCH};
                """
            )


def reverse_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"DROP POLICY IF EXISTS {_policy_name(table)} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("sync_engine", "0019_rollout_policy"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls),
    ]
