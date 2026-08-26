"""Idempotent schema repairs for people app tables (django-tenants drift)."""

from __future__ import annotations

from django.db import connection
from django.utils import timezone


def ensure_teacherprofile_updated_at_column() -> bool:
    """Add ``people_teacherprofile.updated_at`` when the table exists but the column does not.

    Returns True when a column was added, False when already present or table missing.
    Safe to run repeatedly (public schema legacy tables + tenant schemas).
    """
    table_name = "people_teacherprofile"
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return False
        columns = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }

    if "updated_at" in columns:
        return False

    now = timezone.now()
    if connection.vendor == "postgresql":
        q_table = connection.ops.quote_name(table_name)
        q_col = connection.ops.quote_name("updated_at")
        with connection.cursor() as cursor:
            # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
            cursor.execute(
                f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} "
                "timestamp with time zone;"
            )
            # rls-bypass-allow: schema-repair-backfill-of-new-column-runs-once-pre-rls
            cursor.execute(
                f"UPDATE {q_table} SET {q_col} = %s WHERE {q_col} IS NULL;",
                [now],
            )
            # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-enforce-not-null
            cursor.execute(
                f"ALTER TABLE {q_table} ALTER COLUMN {q_col} SET NOT NULL;"
            )
        return True

    # SQLite / other: delegate to Django schema editor when table exists without column.
    from apps.people.models import TeacherProfile

    field = TeacherProfile._meta.get_field("updated_at")
    with connection.schema_editor() as editor:
        editor.add_field(TeacherProfile, field)
    # tenant-isolation-allow: schema-repair-updates-nullable-rows-in-active-tenant-db
    TeacherProfile.objects.filter(updated_at__isnull=True).update(updated_at=now)
    return True


# (db_table, model attr, partial-unique-index name) for every people table that
# migration 0057 added ``client_offline_id`` + a per-school partial unique index
# to. A tenant schema that never received 0057 (provisioned before it landed, or
# whose django-tenants migrate fell short) is missing these and HARD-500s on any
# TeacherProfile / StudentProfile / Applicant query — e.g. ProgrammingError:
# column people_teacherprofile.client_offline_id does not exist.
_OFFLINE_SYNC_TABLES = (
    ("people_teacherprofile", "TeacherProfile", "uniq_teacherprofile_school_offline_id"),
    ("people_studentprofile", "StudentProfile", "uniq_studentprofile_school_offline_id"),
    ("people_applicant", "Applicant", "uniq_applicant_school_offline_id"),
)


def ensure_people_offline_sync_columns() -> bool:
    """Add the ``client_offline_id`` column (+ its partial unique index) to the
    people offline-sync tables when migration 0057 never reached this schema.

    Idempotent: ``ADD COLUMN IF NOT EXISTS`` / ``CREATE UNIQUE INDEX IF NOT
    EXISTS`` mirror exactly what 0057 applies, so this is a no-op on healthy
    tenants and safe to run repeatedly (and to run BEFORE or AFTER 0057 in the
    migration graph — no collision either way). Returns True if anything changed.
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
                    # rls-bypass-allow: drop the helper default so the resulting schema
                    # matches 0057's state (Django adds the column then drops the default).
                    cursor.execute(
                        f"ALTER TABLE {q_table} ALTER COLUMN {q_col} DROP DEFAULT;"
                    )
                changed = True
            # Partial per-school unique index (Django UniqueConstraint w/ condition
            # ~Q(client_offline_id="") → CREATE UNIQUE INDEX … WHERE col <> '').
            q_index = connection.ops.quote_name(index_name)
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-index
                cursor.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {q_index} ON {q_table} "
                    "(school_id, client_offline_id) WHERE client_offline_id <> '';"
                )
        return changed

    # SQLite / other: delegate to the Django schema editor per model field.
    import apps.people.models as people_models

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
        model = getattr(people_models, model_attr, None)
        if model is None:
            continue
        field = model._meta.get_field("client_offline_id")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed


# Migration 0064/0068 merge-tombstone columns. Legacy ``people_*`` tables left in
# the public schema never receive ``migrate_schemas --tenant``, so they can lack
# ``merged_into_id`` (and guardian ``is_active``) while Django's model expects them
# — e.g. ensure_all_user_identities → TeacherProfile.objects.get_or_create 500s.
_MERGE_TOMBSTONE_TABLES = (
    ("people_teacherprofile", "TeacherProfile", "merged_into"),
    ("people_studentprofile", "StudentProfile", "merged_into"),
    ("people_studentguardian", "StudentGuardian", "merged_into"),
)


def _table_columns(table_name: str) -> set[str]:
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return set()
        return {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }


def ensure_people_merge_tombstone_columns() -> bool:
    """Add merge tombstone columns when migration 0064/0068 never reached this schema.

    Returns True when any column was added, False when already present or tables absent.
    """
    changed = False

    if connection.vendor == "postgresql":
        for table, _model_attr, _field_name in _MERGE_TOMBSTONE_TABLES:
            cols = _table_columns(table)
            if not cols or "merged_into_id" in cols:
                continue
            q_table = connection.ops.quote_name(table)
            q_col = connection.ops.quote_name("merged_into_id")
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                cursor.execute(
                    f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} bigint NULL;"
                )
            changed = True

        guardian_cols = _table_columns("people_studentguardian")
        if guardian_cols and "is_active" not in guardian_cols:
            q_table = connection.ops.quote_name("people_studentguardian")
            q_col = connection.ops.quote_name("is_active")
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                cursor.execute(
                    f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} "
                    "boolean NOT NULL DEFAULT true;"
                )
                cursor.execute(
                    f"ALTER TABLE {q_table} ALTER COLUMN {q_col} DROP DEFAULT;"
                )
            changed = True
        return changed

    import apps.people.models as people_models

    for table, model_attr, field_name in _MERGE_TOMBSTONE_TABLES:
        cols = _table_columns(table)
        if not cols or "merged_into_id" in cols:
            continue
        model = getattr(people_models, model_attr, None)
        if model is None:
            continue
        field = model._meta.get_field(field_name)
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True

    guardian_cols = _table_columns("people_studentguardian")
    if guardian_cols and "is_active" not in guardian_cols:
        model = people_models.StudentGuardian
        field = model._meta.get_field("is_active")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed


def ensure_people_schema_current() -> bool:
    """Run every idempotent people-table schema repair. Returns True if any ran."""
    healed_updated_at = ensure_teacherprofile_updated_at_column()
    healed_offline = ensure_people_offline_sync_columns()
    healed_merge = ensure_people_merge_tombstone_columns()
    return bool(healed_updated_at or healed_offline or healed_merge)
