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
