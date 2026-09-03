"""Idempotent schema repairs for academics app tables (django-tenants drift)."""

from __future__ import annotations

from django.db import connection


# Models that gained a nullable ``school`` FK in academics 0028_add_school_fk.
_SCHOOL_FK_MODEL_ATTRS = (
    "AcademicYear",
    "Attendance",
    "CertificationDocumentChecklist",
    "CertificationExamPreset",
    "CertificationExamSession",
    "CertificationFeeTemplate",
    "ClassBooklist",
    "Classroom",
    "ClassroomPromotionMapping",
    "CurriculumStandard",
    "Department",
    "Specialty",
    "Subject",
    "SubjectAssignment",
    "Term",
)


def _table_columns(table_name: str) -> set[str]:
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return set()
        return {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }


def ensure_academics_school_id_columns() -> bool:
    """Add ``school_id`` to academics tables when 0028 never reached this schema.

    Tenant schemas provisioned before 0028 landed (or whose migrate fell short
    while django_migrations already records 0028) 500 with
    ``column academics_academicyear.school_id does not exist``. Idempotent:
    skips tables/columns that already exist.
    """
    import apps.academics.models as academics_models

    changed = False
    for model_attr in _SCHOOL_FK_MODEL_ATTRS:
        model = getattr(academics_models, model_attr, None)
        if model is None:
            continue
        table = model._meta.db_table
        if "school_id" in _table_columns(table):
            continue
        field = model._meta.get_field("school")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed


# (db_table, model attr, partial-unique-index name) for every academics table that
# migration 0073 added ``client_offline_id`` + a per-school partial unique index to.
# A tenant schema that never received 0073 (provisioned before it landed, or whose
# django-tenants migrate fell short while django_migrations already records 0073) is
# missing these and HARD-500s on any Classroom / Attendance query — e.g.
# ``column academics_attendance.client_offline_id does not exist``. Mirrors
# apps/people/schema_repair.py::ensure_people_offline_sync_columns.
_OFFLINE_SYNC_TABLES = (
    ("academics_classroom", "Classroom", "uniq_classroom_school_offline_id"),
    ("academics_attendance", "Attendance", "uniq_attendance_school_offline_id"),
)


def ensure_academics_offline_sync_columns() -> bool:
    """Add ``client_offline_id`` (+ its per-school partial unique index) to the
    academics offline-sync tables when migration 0073 never reached this schema.

    Idempotent: ``ADD COLUMN IF NOT EXISTS`` / ``CREATE UNIQUE INDEX IF NOT EXISTS``
    mirror exactly what 0073 applies, so this is a no-op on healthy tenants and safe
    to run repeatedly (and whether 0073 is applied, fake-applied, or unapplied in
    this schema). Returns True when anything changed.
    """
    changed = False

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
        for table, _model_attr, index_name in _OFFLINE_SYNC_TABLES:
            if table not in existing_tables:
                continue
            q_table = connection.ops.quote_name(table)
            q_col = connection.ops.quote_name("client_offline_id")
            if "client_offline_id" not in _table_columns(table):
                with connection.cursor() as cursor:
                    # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                    cursor.execute(
                        f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} "
                        "varchar(128) NOT NULL DEFAULT '';"
                    )
                    # rls-bypass-allow: drop the helper default so the schema matches 0073.
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
    import apps.academics.models as academics_models

    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
    for table, model_attr, _index_name in _OFFLINE_SYNC_TABLES:
        if table not in existing_tables:
            continue
        if "client_offline_id" in _table_columns(table):
            continue
        model = getattr(academics_models, model_attr, None)
        if model is None:
            continue
        field = model._meta.get_field("client_offline_id")
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        changed = True
    return changed


# Migration 0075 / 0080 catalog edge-sync columns. A tenant whose django_migrations
# records those migrations but whose DDL never landed 500s any full-model Department
# query with ``column academics_department.updated_at does not exist``.
_CATALOG_SYNC_SPECS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "academics_department",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
    (
        "academics_specialty",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
    (
        "academics_subject",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
    (
        "academics_specialtysubject",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
    (
        "academics_academicyear",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
    (
        "academics_term",
        (
            ("client_offline_id", "varchar(128) NOT NULL DEFAULT ''"),
            ("updated_at", "timestamp with time zone NULL"),
        ),
    ),
)


def ensure_academics_catalog_sync_columns() -> bool:
    """Add 0075/0080 ``updated_at`` + ``client_offline_id`` when missing in this schema."""
    if connection.vendor != "postgresql":
        import apps.academics.models as academics_models

        changed = False
        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
        model_by_table = {
            model._meta.db_table: model
            for model in (
                academics_models.Department,
                academics_models.Specialty,
                academics_models.Subject,
                academics_models.SpecialtySubject,
                academics_models.AcademicYear,
                academics_models.Term,
            )
        }
        for table, _specs in _CATALOG_SYNC_SPECS:
            if table not in existing_tables:
                continue
            model = model_by_table.get(table)
            if model is None:
                continue
            cols = _table_columns(table)
            for field_name in ("client_offline_id", "updated_at"):
                if field_name in cols:
                    continue
                field = model._meta.get_field(field_name)
                with connection.schema_editor() as editor:
                    editor.add_field(model, field)
                changed = True
        return changed

    changed = False
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
    for table, columns in _CATALOG_SYNC_SPECS:
        if table not in existing_tables:
            continue
        q_table = connection.ops.quote_name(table)
        live_cols = _table_columns(table)
        for col_name, col_type in columns:
            if col_name in live_cols:
                continue
            q_col = connection.ops.quote_name(col_name)
            with connection.cursor() as cursor:
                # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                cursor.execute(
                    f"ALTER TABLE {q_table} ADD COLUMN IF NOT EXISTS {q_col} {col_type};"
                )
                if col_name == "client_offline_id":
                    # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
                    cursor.execute(
                        f"ALTER TABLE {q_table} ALTER COLUMN {q_col} DROP DEFAULT;"
                    )
            changed = True
    return changed
