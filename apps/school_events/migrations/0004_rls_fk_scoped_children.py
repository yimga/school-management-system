# RLS for school_events' FK-scoped child tables (PostgreSQL single-schema mode only).
#
# 0002/0003 enumerate only the three school_events models that carry a literal
# school FK (EventVenue, EventSponsor, SchoolEvent). EventTicketTier,
# EventSponsorCommitment and EventRegistration hold tenant data too -- ticket
# pricing and stock, sponsor pledge amounts, and every attendee's registration
# with its purchaser and PSP references -- but they reach their school through
# ``event``, so they were in neither list: no ENABLE, no policy, no FORCE. Under
# USE_DJANGO_TENANTS=0 that means any tenant connection could
# `SELECT * FROM school_events_eventregistration` and read every school's rows.
#
# Nothing flagged it, and that is the more important half: the RLS coverage gate
# (scripts/scan_rls_table_coverage.py) decides a model is tenant-scoped by looking
# for a FK literally named ``school``, so a child that reaches its tenant through
# a parent is invisible to it. The gate reports 0 findings and is telling the
# truth about the question it asks.
#
# feedback/0010 and communication/0031 already established the FK-scoped policy
# shape; this mirrors them. All three parents here are NON-nullable, so unlike
# feedback's children there is no orphan case to reason about -- a row always has
# exactly one path to a school.
#
# ENABLE + CREATE POLICY + FORCE all happen here, as in feedback/0010: this
# migration lands after both global FORCE sweeps (schools/0048, schools/0083), so
# neither can cover these tables, and an un-FORCE'd policy does not apply to the
# table owner -- which is the role Django runs as in RLS mode.
#
# No-op on SQLite and under USE_DJANGO_TENANTS=True (schema-per-tenant, where
# search_path is the boundary and RLS is unused).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

POLICY_PREFIX = "school_events_tenant"

# {table: [(parent_table, fk_column), ...]} -- the row belongs to the active
# school when its parent does.
FK_SCOPED_TABLES = {
    "school_events_eventtickettier": [
        ("school_events_schoolevent", "event_id"),
    ],
    "school_events_eventsponsorcommitment": [
        ("school_events_schoolevent", "event_id"),
    ],
    "school_events_eventregistration": [
        ("school_events_schoolevent", "event_id"),
    ],
}


def _using_clause(table, parents):
    exists = "\n    OR ".join(
        f"""EXISTS (
        SELECT 1 FROM {parent} p{index}
        WHERE p{index}.id = {table}.{fk}
          AND current_setting('app.current_school_id', true) IS NOT NULL
          AND p{index}.school_id::text = current_setting('app.current_school_id', true)
    )"""
        for index, (parent, fk) in enumerate(parents)
    )
    return f"""(
    current_setting('app.rls_bypass', true) = 'on'
    OR {exists}
)"""


def _existing(cursor, tables):
    # Mirrors feedback/0010: a table absent from this schema is skipped rather
    # than aborting the whole migration.
    cursor.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname = current_schema()
          AND c.relname = ANY(%s)
        """,
        [list(tables)],
    )
    return {row[0] for row in cursor.fetchall()}


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        present = _existing(cursor, list(FK_SCOPED_TABLES))
        for table, parents in FK_SCOPED_TABLES.items():
            if table not in present:
                continue
            suffix = table.replace("school_events_", "", 1)
            policy_name = f"{POLICY_PREFIX}_{suffix}"
            using = _using_clause(table, parents)
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {using}
                WITH CHECK {using};
                """
            )
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        present = _existing(cursor, list(FK_SCOPED_TABLES))
        for table in FK_SCOPED_TABLES:
            if table not in present:
                continue
            suffix = table.replace("school_events_", "", 1)
            cursor.execute(
                f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{suffix} ON {table};"
            )
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("school_events", "0003_rls_policy_default_deny"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
