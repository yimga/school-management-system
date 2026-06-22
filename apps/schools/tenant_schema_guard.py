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

# Dispatching a per-app column repair can additionally fail to import (app not
# installed in this deployment) or be missing its entrypoint — both mean "skip
# this repair", never "abort provisioning".
_REPAIR_DISPATCH_ERRORS = _HEAL_ERRORS + (ImportError, AttributeError)


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


def missing_tenant_columns(conn=None) -> list[tuple[str, str, str, str]]:
    """READ-ONLY: tenant-app columns absent from an EXISTING table in this schema.

    Returns a sorted list of (app_label, model_name, db_table, column). This is the
    drift class ``missing_tenant_tables`` cannot see: an ``AddField`` recorded as
    applied whose column never physically landed (e.g.
    ``finance_notification.dismissed_at``), which 500s any query that selects it.
    Tables that are missing entirely are skipped here — that is
    ``missing_tenant_tables``' job. Run inside ``tenant_context`` / ``schema_context``.
    """
    conn = conn or connection
    with conn.cursor() as cursor:
        existing_tables = set(conn.introspection.table_names(cursor))
    missing: list[tuple[str, str, str, str]] = []
    for model in _managed_tenant_models():
        table = model._meta.db_table
        if table not in existing_tables:
            continue
        with conn.cursor() as cursor:
            cols = {
                col.name
                for col in conn.introspection.get_table_description(cursor, table)
            }
        for field in model._meta.local_concrete_fields:
            column = field.column
            if column and column not in cols:
                missing.append(
                    (model._meta.app_label, model.__name__, table, column)
                )
    return sorted(missing)


def scan_all_tenant_schemas(only_schema=None) -> dict[str, list[tuple[str, str, str]]]:
    """Run ``missing_tenant_tables`` against every tenant schema (or just one).

    Returns ``{schema_name: [(app, model, table), ...]}``. Shared single source of
    truth for both ``manage.py detect_tenant_table_drift`` and the periodic beat
    task. Under shared-DB / RLS mode (no django-tenants) there is a single schema,
    reported as ``{"public": ...}``.
    """
    try:
        from django_tenants.utils import get_tenant_model, schema_context
    except ImportError:
        return {"public": missing_tenant_tables()}

    report: dict[str, list[tuple[str, str, str]]] = {}
    qs = get_tenant_model().objects.exclude(schema_name="public")
    if only_schema:
        qs = qs.filter(schema_name=only_schema)
    for client in qs.order_by("schema_name"):
        with schema_context(client.schema_name):
            report[client.schema_name] = missing_tenant_tables()
    return report


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


def ensure_models_columns(schema_editor, models) -> list[str]:
    """Best-effort add of any missing column among ``models`` in the current schema.

    The column-granularity twin of ``ensure_models_tables``: heals the generic
    drift class (an ``AddField`` recorded as applied whose column never landed)
    for ANY tenant model, not just the hand-written per-app repairs in
    ``_COLUMN_REPAIRS``. Each field is added in its OWN savepoint, so one failure
    (e.g. a NOT NULL add on a populated table) is logged and skipped and never
    aborts the rest. Tables that are missing entirely are skipped (that is
    ``ensure_models_tables``' job). Returns the ``"table.column"`` list actually
    added; a no-op on a healthy schema.
    """
    conn = schema_editor.connection
    schema_name = getattr(conn, "schema_name", "?")
    with conn.cursor() as cursor:
        existing_tables = set(conn.introspection.table_names(cursor))
    added: list[str] = []
    for model in models:
        table = model._meta.db_table
        if table not in existing_tables:
            continue
        with conn.cursor() as cursor:
            cols = {
                col.name
                for col in conn.introspection.get_table_description(cursor, table)
            }
        for field in model._meta.local_concrete_fields:
            column = field.column
            if not column or column in cols:
                continue
            try:
                with transaction.atomic(using=conn.alias):
                    schema_editor.add_field(model, field)
                added.append(f"{table}.{column}")
                logger.warning(
                    "tenant_schema_guard: added missing column %s.%s in schema %s",
                    table,
                    column,
                    schema_name,
                )
            except _HEAL_ERRORS as exc:
                logger.exception(
                    "tenant_schema_guard: could not add column %s.%s in schema %s "
                    "(left for a full migrate): %s",
                    table,
                    column,
                    schema_name,
                    exc,
                )
    return added


# Per-app COLUMN-drift heals. Each entry is (label, module path, callable name).
# These heals introspect the LIVE table columns (NOT django_migrations), so they
# fix the drift class that `migrate` cannot: a heal migration recorded as applied
# whose AddField never physically landed in the schema. That is exactly the
# `column academics_academicyear.school_id does not exist` failure that aborts the
# provisioning seed_data step and 500s the owner dashboard. Keep this list in sync
# as new per-app schema_repair entrypoints land. NOTE: only true COLUMN heals
# belong here — index/dedup heals (e.g. finance OfflinePaymentIntent) run their own
# write and are owned by their app's migration, so they are deliberately excluded.
_COLUMN_REPAIRS: tuple[tuple[str, str, str], ...] = (
    ("academics_school_id", "apps.academics.schema_repair", "ensure_academics_school_id_columns"),
    ("people_schema", "apps.people.schema_repair", "ensure_people_schema_current"),
    ("schoolops_visitorcheckin_offline_id", "apps.schoolops.schema_repair", "ensure_visitorcheckin_offline_id_column"),
    # Notification.dismissed_at/expires_at/school_id from finance 0071 — the drift
    # that 500'd /api/notifications/unread_count/ on every authenticated page. This
    # is a TRUE column heal; the finance OfflinePaymentIntent INDEX heal stays out
    # of this list (it is owned by its own migration) per the note above.
    ("finance_notification_columns", "apps.finance.schema_repair", "ensure_finance_notification_columns"),
)


def run_tenant_column_repairs() -> dict[str, bool]:
    """Best-effort idempotent COLUMN-drift heal for the CURRENT schema.

    Complements ``ensure_models_tables`` (table granularity) and the provision-time
    ``migrate``. Run this inside the tenant boundary (``tenant_context`` / RLS pin)
    BEFORE the first tenant-scoped seed query so a requeue can actually REPAIR a
    ``column ... does not exist`` failure instead of looping on it. Each repair runs
    independently — an import/DDL failure in one is logged and skipped, never
    aborting the others or provisioning. Idempotent: a no-op on a healthy schema
    (one introspection per table). Returns ``{label: changed_bool}`` for the repairs
    that ran to completion.
    """
    from importlib import import_module

    results: dict[str, bool] = {}
    for label, module_path, func_name in _COLUMN_REPAIRS:
        try:
            repair = getattr(import_module(module_path), func_name)
            results[label] = bool(repair())
        except _REPAIR_DISPATCH_ERRORS as exc:
            logger.exception(
                "tenant_schema_guard: column repair %s failed (skipped): %s",
                label,
                exc,
            )
    return results
