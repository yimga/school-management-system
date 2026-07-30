"""Idempotent schema repairs for schools offline-sync columns (schema drift).

Mirror of apps/people/schema_repair.py + apps/schoolops/schema_repair.py for the
advancement offline-capture columns. ``AdvancementGift`` and ``InKindDonation``
had ``client_offline_id`` (+ a partial unique index) ADDED to their pre-existing
tables via AddField in migration ``0070_advancementgift_client_offline_id_and_more``
— the same heal-able drift family as people/0059 and schoolops/0022. A schema that
never received 0070 (a faked migration, an older public-schema restore, a partial
deploy) is missing the column and HARD-500s on any AdvancementGift / InKindDonation
query. This heals it with ADD COLUMN / CREATE UNIQUE INDEX IF NOT EXISTS forms, so
it is a no-op on healthy schemas and never collides with 0070 on migration replay.

``apps.schools`` is a SHARED app, so these tables live in the public schema and the
heal runs under ``migrate_schemas --shared`` (predeploy) rather than ``--tenant``.
"""

from __future__ import annotations

from django.db import connection

# (model attr, partial-unique-index name, scope column) — schools tables that had
# ``client_offline_id`` ADDED to a pre-existing table via AddField (the heal-able
# drift). Each partial unique index scopes offline-id uniqueness differently:
# AdvancementGift dedupes per donor, InKindDonation per school.
_OFFLINE_SYNC_SPECS = (
    ("AdvancementGift", "uniq_advancementgift_donor_client_offline_id", "donor_id"),
    ("InKindDonation", "uniq_inkinddonation_school_client_offline_id", "school_id"),
)


def ensure_advancement_offline_id_columns() -> bool:
    """Add ``client_offline_id`` (+ its partial unique index) to the schools
    advancement offline-sync tables when migration 0070 never reached this schema.

    Idempotent; returns True if anything changed.
    """
    import apps.schools.models as schools_models

    changed = False
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))

    if connection.vendor == "postgresql":
        for model_attr, index_name, scope_col in _OFFLINE_SYNC_SPECS:
            model = getattr(schools_models, model_attr, None)
            if model is None:
                continue
            table = model._meta.db_table
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
                        "varchar(64) NOT NULL DEFAULT '';"
                    )
                    # rls-bypass-allow: drop the helper default so the schema matches 0070's state
                    cursor.execute(
                        f"ALTER TABLE {q_table} ALTER COLUMN {q_col} DROP DEFAULT;"
                    )
                changed = True
            q_index = connection.ops.quote_name(index_name)
            q_scope = connection.ops.quote_name(scope_col)
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-index
                cursor.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {q_index} ON {q_table} "
                    f"({q_scope}, client_offline_id) WHERE client_offline_id <> '';"
                )
        return changed

    # SQLite / other: delegate to the Django schema editor per model field.
    for model_attr, _index_name, _scope_col in _OFFLINE_SYNC_SPECS:
        model = getattr(schools_models, model_attr, None)
        if model is None:
            continue
        table = model._meta.db_table
        if table not in existing_tables:
            continue
        with connection.cursor() as cursor:
            cols = {
                col.name
                for col in connection.introspection.get_table_description(cursor, table)
            }
        if "client_offline_id" in cols:
            continue
        field = model._meta.get_field("client_offline_id")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed
