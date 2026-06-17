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
