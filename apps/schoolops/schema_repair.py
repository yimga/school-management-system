"""Idempotent schema repairs for schoolops tables (django-tenants drift).

Mirror of apps/people/schema_repair.py for the schoolops offline-sync columns.
A tenant schema provisioned before — or that never received — migration
``0022_visitorcheckin_client_offline_id`` (+ the ``0023`` partial unique index)
is missing ``schools_visitorcheckin.client_offline_id`` and HARD-500s on any
VisitorCheckIn query, exactly like the people_teacherprofile.client_offline_id
drift. This heals it with the same ADD COLUMN / CREATE UNIQUE INDEX IF NOT EXISTS
forms, so it is a no-op on healthy schemas and never collides with 0022/0023 on
migration replay.
"""

from __future__ import annotations

from django.db import connection

# (db_table, model attr, partial-unique-index name) — schoolops tables that had
# ``client_offline_id`` ADDED to a pre-existing table via AddField (the heal-able
# drift). Tables that were CREATED with the column drift as a missing TABLE, which
# is a migrate concern, not a column-patch — those are deliberately excluded.
_OFFLINE_SYNC_TABLES = (
    ("schools_visitorcheckin", "VisitorCheckIn", "uniq_visitorcheckin_school_offline_id"),
)


def ensure_visitorcheckin_offline_id_column() -> bool:
    """Add ``client_offline_id`` (+ its partial unique index) to the schoolops
    offline-sync tables when migration 0022/0023 never reached this schema.

    Idempotent; returns True if anything changed.
    """
    changed = False

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
        for table, _model_attr, index_name in _OFFLINE_SYNC_TABLES:
            if table not in existing_tables:
                continue
            with connection.cursor() as cursor:
                cols = {
                    col.name
                    for col in connection.introspection.get_table_description(
                        cursor, table
                    )
                }
            q_table = connection.ops.quote_name(table)
            q_col = connection.ops.quote_name("client_offline_id")
            if "client_offline_id" not in cols:
                with connection.cursor() as cursor:
                    # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                    cursor.execute(
                        f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} "
                        "varchar(128) NOT NULL DEFAULT '';"
                    )
                    # rls-bypass-allow: drop the helper default so the schema matches 0022's state
                    cursor.execute(
                        f"ALTER TABLE {q_table} ALTER COLUMN {q_col} DROP DEFAULT;"
                    )
                changed = True
            q_index = connection.ops.quote_name(index_name)
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-index
                cursor.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {q_index} ON {q_table} "
                    "(school_id, client_offline_id) WHERE client_offline_id <> '';"
                )
        return changed

    # SQLite / other: delegate to the Django schema editor per model field.
    import apps.schoolops.models as schoolops_models

    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
    for table, model_attr, _index_name in _OFFLINE_SYNC_TABLES:
        if table not in existing_tables:
            continue
        with connection.cursor() as cursor:
            cols = {
                col.name
                for col in connection.introspection.get_table_description(cursor, table)
            }
        if "client_offline_id" in cols:
            continue
        model = getattr(schoolops_models, model_attr, None)
        if model is None:
            continue
        field = model._meta.get_field("client_offline_id")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed
