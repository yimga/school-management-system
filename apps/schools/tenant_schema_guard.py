"""Tenant-schema table-drift detection + best-effort table heal (django-tenants).

The recurring prod failure class is schema-per-tenant drift: a migration that
never reached a tenant schema. Missing COLUMNS (AddField onto a live table) are
healed by the per-column schema_repair modules (apps/people/schema_repair.py,
apps/schoolops/schema_repair.py). This module covers the TABLE granularity — the
rarer "fake-applied CreateModel" case where the migration is recorded as applied
but the table was never created, so `migrate_schemas --tenant` skips it and any
query 500s with "relation does not exist".

Two entry points:

* ``missing_tenant_tables()`` — READ-ONLY. Which tenant-app tables are absent from
  the current schema. Powers ``manage.py detect_tenant_table_drift``.
* ``ensure_models_tables()`` — best-effort create of missing tables via the schema
  editor, for the forward "ensure-exists" heal migrations. Each model is created
  inside its OWN savepoint with its deferred FK SQL flushed in-place, so a single
  failure (e.g. an FK target that is itself missing) is logged and skipped and can
  NEVER abort ``migrate_schemas --tenant`` or a deploy.
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.db import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
    connection,
    transaction,
)

logger = logging.getLogger(__name__)

_HEAL_ERRORS = (
    DatabaseError,
    OperationalError,
    ProgrammingError,
    IntegrityError,
    ValueError,
    TypeError,
)


def _entry_to_app_name(entry: str) -> str:
    """Normalise an INSTALLED_APPS-style entry to its app module name.

    "apps.feedback.apps.FeedbackConfig" -> "apps.feedback"; "apps.people" stays.
    """
    if entry.endswith("Config") and ".apps." in entry:
        return entry.rsplit(".apps.", 1)[0]
    return entry


def tenant_app_labels() -> set[str]:
    """App labels that live ONLY in tenant schemas (TENANT_APPS minus SHARED_APPS)."""
    tenant_names = {_entry_to_app_name(e) for e in getattr(settings, "TENANT_APPS", [])}
    shared_names = {_entry_to_app_name(e) for e in getattr(settings, "SHARED_APPS", [])}
    tenant_only = tenant_names - shared_names
    return {
        cfg.label
        for cfg in django_apps.get_app_configs()
        if cfg.name in tenant_only
    }


def _managed_tenant_models():
    labels = tenant_app_labels()
    for model in django_apps.get_models():
        meta = model._meta
        if meta.app_label not in labels:
            continue
        if not meta.managed or meta.proxy:
            continue
        yield model


def missing_tenant_tables(conn=None) -> list[tuple[str, str, str]]:
    """READ-ONLY: tenant-app model tables absent from the current schema.

    Returns a sorted list of (app_label, model_name, db_table). Empty when healthy.
    Run inside ``tenant_context(client)`` / ``schema_context(name)`` to scope it to
    one tenant schema.
    """
    conn = conn or connection
    with conn.cursor() as cursor:
        existing = set(conn.introspection.table_names(cursor))
    missing = [
        (model._meta.app_label, model.__name__, model._meta.db_table)
        for model in _managed_tenant_models()
        if model._meta.db_table not in existing
    ]
    return sorted(missing)


def ensure_models_tables(schema_editor, models) -> list[str]:
    """Best-effort create of any missing table among ``models`` in the current schema.

    Each model is created in its own savepoint and its deferred FK/constraint SQL is
    executed in-place, so a failure (missing FK target, etc.) rolls back just that
    model, is logged, and is skipped — it never aborts the migration / deploy.
    Returns the list of tables actually created. No-op for tables that already exist.
    """
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        existing = set(conn.introspection.table_names(cursor))
    schema_name = getattr(conn, "schema_name", "?")
    created: list[str] = []
    for model in models:
        table = model._meta.db_table
        if table in existing:
            continue
        try:
            with transaction.atomic(using=conn.alias):
                before = len(schema_editor.deferred_sql)
                schema_editor.create_model(model)
                # Flush THIS model's deferred FK/constraint SQL now so a bad FK
                # target fails inside our savepoint instead of later aborting the
                # whole migration when the schema editor flushes deferred_sql.
                pending = schema_editor.deferred_sql[before:]
                del schema_editor.deferred_sql[before:]
                for sql in pending:
                    schema_editor.execute(sql)
            created.append(table)
            logger.warning(
                "tenant_schema_guard: created missing table %s in schema %s",
                table,
                schema_name,
            )
        except _HEAL_ERRORS as exc:
            logger.exception(
                "tenant_schema_guard: could not create missing table %s in schema "
                "%s (left for a full migrate): %s",
                table,
                schema_name,
                exc,
            )
    return created
