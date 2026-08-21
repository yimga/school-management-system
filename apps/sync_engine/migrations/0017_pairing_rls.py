# RLS for the three tenant-scoped tables the pairing wave (PR #184) added.
#
# `scan_rls_table_coverage.py` is a ZERO-baseline gate wired into ci.yml, and it went red
# the moment PR #184 merged: `EdgePairingRequest`, `PendingPushConfirmation` and
# `EdgeClaimTicket` all carry a `school` FK, and none was named in any enable_rls
# migration. The app-level sibling (`scan_rls_force_coverage`) stayed green throughout,
# because `sync_engine/migrations/` already contains 0008 and 0009 -- it asks whether the
# APP has RLS migrations, not whether THIS TABLE is in one. Nothing else caught it either:
# GitHub Actions has run no jobs since 2026-08-15, and `pre_push_boundary_check.py` is
# deps-free by design so it cannot run a gate that needs the Django app registry.
#
# SCOPE, stated so this is not over-read: `should_apply_rls` returns False under
# USE_DJANGO_TENANTS, which render.yaml sets, so this is a NO-OP in the deployed
# schema-per-tenant topology -- isolation there is Postgres schemas plus service-layer
# `school=` scoping. What this migration buys is RLS-MODE READINESS: the work that has to
# be in place before anyone runs with USE_DJANGO_TENANTS=0 on PostgreSQL, where RLS *is*
# the isolation and an unenumerated table has none at all.
#
# TWO POLICY SHAPES, on purpose.
#
# `EdgePairingRequest.school` is NULLABLE by design: a box that names a slug the cloud
# does not recognise still produces a request row, so that the operator sees a real
# pairing attempt instead of silence. Under the strict policy `school_id = current`, a
# NULL never compares equal, so those rows would become invisible to everyone -- and the
# claim flow is a lookup BY USER_CODE (`pairing_service.claim_by_code`), which is exactly
# the query that would then find nothing. Pairing would break in RLS mode, in a way no
# SQLite test can show. So the policy for that one table also admits `school_id IS NULL`.
#
# That is not a hole: an unclaimed request belongs to no tenant yet, the user code IS the
# secret that authorises claiming it, and `may_adopt_for()` re-derives the caller's
# standing against the request's own school before anything is minted. Once a request is
# bound to a school it stops being NULL and the ordinary tenant check applies.
#
# The other two are NOT NULL and get the strict policy with no exception.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

# school_id NOT NULL -- the ordinary tenant predicate.
STRICT_TABLES = [
    "sync_engine_pendingpushconfirmation",
    "sync_engine_edgeclaimticket",
]

# school_id NULLABLE -- see the note above.
NULLABLE_SCHOOL_TABLES = [
    "sync_engine_edgepairingrequest",
]

TABLES = STRICT_TABLES + NULLABLE_SCHOOL_TABLES

_TENANT_MATCH = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""

_TENANT_MATCH_OR_UNCLAIMED = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR school_id IS NULL
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
            using = (
                _TENANT_MATCH_OR_UNCLAIMED
                if table in NULLABLE_SCHOOL_TABLES
                else _TENANT_MATCH
            )
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
                USING {using}
                WITH CHECK {using};
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
        ("sync_engine", "0016_syncpolicy_rls"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls),
    ]
