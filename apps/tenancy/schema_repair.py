"""Generic idempotent heal for tenant-app ``school`` FK columns (django-tenants drift).

The tenant-isolation wave retrofitted a nullable ``school`` FK onto many
tenant-app models via ``AddField`` migrations (academics 0028 + 0031/Incident,
people 0024, finance 0036, evals 0023, reports 0008, communication 0009,
portal 0023/0033, ...). A tenant schema provisioned by cloning a recorded
migration state — or whose migrate fell short while ``django_migrations`` already
records the migration as applied — can carry the record without the column ever
landing. Every ORM query that then selects it 500s with
``column <table>.school_id does not exist`` (the academics AcademicYear incident,
2026-07-13).

``ensure_app_school_id_columns(app_label)`` re-adds the missing ``school`` FK
column for every managed model in ``app_label`` whose CURRENT field set declares
one, but only where the column is genuinely absent — a no-op on healthy schemas,
a one-shot heal on drifted ones. It uses the live model + a fresh
``schema_editor`` (the same approach as ``apps.academics.schema_repair``) because
a repair heals toward the current model state; wrap it in a graph-leaf RunPython
per tenant app so ``migrate_schemas --tenant`` runs it against every schema.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import FieldDoesNotExist
from django.db import connection


def _table_columns(table_name: str) -> set[str]:
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return set()
        return {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }


def _is_school_fk(field) -> bool:
    """True only for a concrete forward FK/O2O named ``school`` -> schools.School."""
    return bool(
        getattr(field, "concrete", False)
        and getattr(field, "is_relation", False)
        and (field.many_to_one or field.one_to_one)
        and getattr(field, "related_model", None) is not None
        and field.related_model._meta.label_lower == "schools.school"
    )


def ensure_app_school_id_columns(app_label: str) -> list[str]:
    """Heal every missing ``school`` FK column for ``app_label`` in THIS schema.

    Returns the ``"<table>.<column>"`` list that was healed (empty on a healthy
    schema). Idempotent and safe to re-run.
    """
    healed: list[str] = []
    try:
        app_config = django_apps.get_app_config(app_label)
    except LookupError:
        return healed

    for model in app_config.get_models():
        if not model._meta.managed:
            continue
        try:
            field = model._meta.get_field("school")
        except FieldDoesNotExist:
            continue
        if not _is_school_fk(field):
            continue
        table = model._meta.db_table
        if field.column in _table_columns(table):
            continue
        with connection.schema_editor() as editor:
            editor.add_field(model, field)
        healed.append(f"{table}.{field.column}")
    return healed
