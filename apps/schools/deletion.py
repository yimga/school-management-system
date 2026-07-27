"""Hard-deleting a ``School`` row from the ``public`` schema.

The problem
-----------
Under ``USE_DJANGO_TENANTS=1`` (what ``render.yaml`` sets) ``apps.schools`` is a
SHARED app living in ``public``, while the ~15 TENANT apps live in one schema PER
tenant. Roughly two hundred tenant models carry a ``school`` ForeignKey — the
normal, legal direction, because a tenant schema's ``search_path`` includes
``public``.

Django's cascade collector does not know any of that. Asked to delete a School it
walks EVERY reverse relation, tenant ones included, and issues a query against a
table that does not exist in ``public``::

    >>> School.objects.filter(slug="example-school").delete()
    ProgrammingError: relation "portal_portalfeatureitem" does not exist

Nothing is deleted — the collector fails while still gathering. Worse, inside an
atomic block that error poisons the whole transaction, so every later statement
fails too.

The fix
-------
`PublicSchemaCollector` skips relations whose model exists only in tenant schemas.
Those rows are not reachable from ``public`` and must not be — a School's tenant
data belongs to its schema, and the schema is dropped or kept as a unit.

Only tenant-per-schema deployments skip anything. Under RLS mode
(``USE_DJANGO_TENANTS=0``) every table lives in one schema, so the stock
collector is already correct and nothing here changes behaviour.

Dropping the schema is a separate, explicit decision. ``Client.auto_drop_schema``
is ``False`` on purpose, so deleting the row never destroys tenant data by
accident. `delete_school` keeps that default and reports the schema it left
behind rather than silently orphaning it.
"""
from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection, router, transaction
from django.db.models.deletion import Collector

logger = logging.getLogger(__name__)

__all__ = [
    "PublicSchemaCollector",
    "TenantSchemaStillPresent",
    "assert_deletable",
    "delete_school",
    "delete_school_rows",
    "is_tenant_only_model",
    "tenant_only_app_labels",
    "tenant_schema_for",
]


class TenantSchemaStillPresent(RuntimeError):
    """Raised when a School cannot be deleted because its schema is still live."""


def _app_label(dotted: str) -> str:
    """``'apps.finance'`` / ``'apps.finance.apps.FinanceConfig'`` -> ``'finance'``."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return ""
    if parts[0] == "apps" and len(parts) >= 2:
        return parts[1]
    return parts[0]


def tenant_only_app_labels() -> frozenset[str]:
    """App labels that exist ONLY in tenant schemas — never in ``public``.

    An app listed in BOTH ``SHARED_APPS`` and ``TENANT_APPS`` is present in
    ``public`` too, so it is not tenant-only and must still cascade.
    """
    shared = {_app_label(x) for x in getattr(settings, "SHARED_APPS", ()) or ()}
    tenant = {_app_label(x) for x in getattr(settings, "TENANT_APPS", ()) or ()}
    return frozenset(tenant - shared)


def is_tenant_only_model(model) -> bool:
    return model._meta.app_label in tenant_only_app_labels()


def _in_public_schema() -> bool:
    """True when the connection is on ``public`` under schema-per-tenant."""
    schema_name = getattr(connection, "schema_name", None)
    if schema_name is None:
        return False  # not the django-tenants backend: RLS mode, one schema
    return schema_name == getattr(
        settings, "PUBLIC_SCHEMA_NAME", "public"
    )


class PublicSchemaCollector(Collector):
    """A collector that does not chase relations into tenant schemas."""

    def __init__(self, *args, skip_tenant_relations: bool | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.skip_tenant_relations = (
            _in_public_schema() if skip_tenant_relations is None else skip_tenant_relations
        )
        # Resolved once: ``related_objects`` runs a few hundred times per delete.
        self.tenant_labels = tenant_only_app_labels() if self.skip_tenant_relations else frozenset()
        self.skipped_models: set[str] = set()

    def related_objects(self, related_model, related_fields, objs):
        if related_model._meta.app_label in self.tenant_labels:
            self.skipped_models.add(related_model._meta.label)
            # Not a lie by omission: these rows live in the tenant schema and are
            # removed with it. An empty queryset never touches the database, so
            # both the fast-delete and the SET_NULL paths become no-ops.
            return related_model._base_manager.none()
        return super().related_objects(related_model, related_fields, objs)


def delete_school_rows(schools, *, using=None) -> tuple[int, dict, list[str]]:
    """Hard-delete School rows, cascading over SHARED relations only.

    Returns Django's ``(count, by_label)`` plus the tenant models that were
    deliberately not chased, so a caller can report them.
    """
    schools = list(schools)
    if not schools:
        return 0, {}, []

    model = schools[0].__class__
    if using is None:
        using = router.db_for_write(model, instance=schools[0])

    collector = PublicSchemaCollector(using=using, origin=schools)
    collector.collect(schools)
    with transaction.atomic(using=using):
        deleted_count, by_label = collector.delete()
    return deleted_count, by_label, sorted(collector.skipped_models)


def _resolve_client(school):
    try:
        client_model = django_apps.get_model("customers", "Client")
    except LookupError:  # pragma: no cover - customers is always installed
        return None
    return client_model.objects.filter(school=school).first()


def _schema_exists(schema_name: str) -> bool:
    if not schema_name or connection.vendor != "postgresql":
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cursor.fetchone() is not None


def tenant_schema_for(school) -> str:
    """The name of the tenant schema this school owns, if it still exists."""
    client = _resolve_client(school)
    schema_name = getattr(client, "schema_name", "") if client is not None else ""
    schema_name = (schema_name or "").strip()
    return schema_name if _schema_exists(schema_name) else ""


def assert_deletable(school) -> None:
    """Refuse to delete a School that still owns a live tenant schema.

    A tenant table's ``school_id`` is a REAL cross-schema foreign key: the tenant
    schema's ``search_path`` spans ``<tenant>, public``, so ``REFERENCES
    schools_school`` binds to the row in ``public``. Deleting that row while the
    schema still holds data would violate those constraints — Postgres would
    refuse, and it would be right to.

    So the schema and the row are deleted together or not at all. This turns what
    used to be a mystifying ``relation "portal_portalfeatureitem" does not exist``
    into a statement of what is actually wrong and what to do about it.
    """
    schema_name = tenant_schema_for(school)
    if not schema_name:
        return
    raise TenantSchemaStillPresent(
        f"School {school.pk} ({getattr(school, 'slug', '')!r}) still owns tenant "
        f"schema {schema_name!r}. Rows in that schema hold cross-schema foreign "
        f"keys to this row, so deleting it alone would violate them. Drop the "
        f"schema in the same operation with "
        f"delete_school(school, drop_schema=True), or offboard the tenant first."
    )


def delete_school(school, *, drop_schema: bool = False) -> dict:
    """Hard-delete ``school``, its SHARED-schema dependents, and optionally its schema.

    Tenant-schema rows are never deleted row-by-row from ``public`` — they are not
    reachable from there. They go with the schema, which is why ``drop_schema`` is
    the only way to delete a provisioned school.

    Returns a summary dict rather than Django's ``(count, by_label)`` tuple,
    because what was skipped matters as much as what was deleted.
    """
    client = _resolve_client(school)
    schema_name = (getattr(client, "schema_name", "") if client is not None else "") or ""

    schema_dropped = False
    if drop_schema and client is not None and _schema_exists(schema_name):
        # Drops the schema AND removes the Client row. Must happen BEFORE the
        # School row goes: ``Client.school`` is CASCADE, so deleting the School
        # first takes the Client with it and orphans the schema forever, with
        # nothing left in the database that names it.
        client.delete(force_drop=True)
        schema_dropped = True

    assert_deletable(school)
    deleted_count, by_label, skipped = delete_school_rows([school])

    return {
        "deleted": deleted_count,
        "by_label": by_label,
        "schema_name": schema_name,
        "schema_dropped": schema_dropped,
        "skipped_tenant_models": skipped,
    }
