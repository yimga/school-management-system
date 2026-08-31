"""Enter a school's OWN tenant schema for a read or a write.

WHY THIS EXISTS
---------------
Under ``USE_DJANGO_TENANTS=1`` (what ``render.yaml`` sets) the TENANT_APPS live in one
PostgreSQL schema **per tenant**, and ``public`` holds the SHARED apps plus whatever
legacy rows predate the split. django-tenants binds a schema from the *request*, so a
management command -- which has no request -- never binds one, and every query it runs
lands on ``public``.

Both portability modules were written without that step, and neither failed loudly:

* ``tenant_portability._scope_queryset`` branches on the flag and returns
  ``model._default_manager.all()``, its comment reasoning "the schema IS the tenant --
  every row belongs to it". True of the tenant schema; the query ran on ``public``, so
  it dropped the school filter *and* stayed on the shared table.
* ``staff_portability`` filtered by ``school`` and so looked safe, but read ``public``'s
  legacy copy of that school's staff rather than the roster the tenant UI serves.

Measured on the deployed cloud, 2026-08-31, for one school:

    public                              56 teachers  (39 tagged for this school,
                                                      16 orphaned, 1 ANOTHER SCHOOL'S)
                                       204 students  (none of them this school's)
    s_f984ea95d2ad4900b51366a345928316  40 teachers, 538 students   <- the live roster

So the unfiltered export shipped one tenant's row inside another tenant's bundle, and
the staff export moved a roster the product does not show.

WHAT THIS DOES
--------------
Nothing at all on a sovereign box: ``USE_DJANGO_TENANTS=0`` means one schema, so there
is no schema to switch into and the previous behaviour is exactly correct there.

On a schema-per-tenant deployment it resolves the school's schema through
``apps.migration_cloud.schema_binding.resolve_school_schema_name`` -- already the single
resolver for intake, bind, companion and apply, and written after Migration Cloud hit
this same class of bug ("landed rows never appear in the tenant school UI") -- and fails
CLOSED if it cannot. An export that quietly falls back to ``public`` is the failure this
module exists to end: it succeeds, writes a valid signed bundle, and carries the wrong
table.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger(__name__)


def schema_per_tenant() -> bool:
    """True when tenant tables live in one schema per tenant (the deployed cloud)."""
    return bool(getattr(settings, "USE_DJANGO_TENANTS", False))


def resolve_schema(school) -> str:
    """The school's tenant schema name, or ``""`` on a single-schema deployment."""
    if not schema_per_tenant():
        return ""
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    return str(resolve_school_schema_name(school) or "").strip()


@contextmanager
def school_schema(school):
    """Run the block against ``school``'s tenant schema. A no-op on a box.

    Yields the schema name actually entered (``""`` when there was none to enter), so a
    caller can record which table it read -- the one fact that distinguishes a correct
    export from the silent-``public`` one.

    Raises ``ValueError`` rather than proceeding on the wrong schema.
    """
    if not schema_per_tenant():
        yield ""
        return

    name = resolve_schema(school)
    if not name:
        raise ValueError(
            "tenant_schema_unresolved: this deployment is schema-per-tenant but no "
            f"schema could be resolved for school {getattr(school, 'pk', '?')}. "
            "Refusing to read or write `public`, which holds a legacy copy and other "
            "tenants' rows. Check customers.Client.schema_name for this school."
        )

    from django_tenants.utils import schema_context

    with schema_context(name):
        yield name


__all__ = ["schema_per_tenant", "resolve_schema", "school_schema"]
