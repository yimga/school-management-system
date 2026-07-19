"""Does this tenant's workspace actually EXIST? — the ground-truth probe.

WHY THIS EXISTS
---------------
``School.is_active`` defaults to ``True`` (``schools.models.School``), so ANY
``School.objects.create(...)`` that skips the provisioning pipeline lands "live"
with no tenant workspace behind it and 500s on every request.

That is not hypothetical, and it is not a one-off: schools migration ``0012``
(legacy default-tenant seed) MANUFACTURES one on every deploy. It is a
single-tenant-era leftover ("Seed default tenant … one existing tenant") that
creates an active+approved school row and never provisions it. Its partner
customers migration ``0003`` (legacy default-tenant domain ensure) then runs a
bare ``CREATE SCHEMA IF NOT EXISTS`` for that tenant with no
``migrate_schemas --tenant`` — so the row can even own an EMPTY schema, which is
why this probe asks whether the schema has TABLES rather than whether it exists.

It was unfixable by ANY tool, because every guard read ``is_active`` as proof of
provisioning:

  * ``resolve_portal_ready`` returned True on the legacy ``is_active`` leg, so
    ``_school_is_settled`` called it settled and every healer skipped it;
  * ``provisioning_needs_resume`` bails without ``phase_a_complete``, so the
    reconciler never saw it;
  * ``can_operator_requeue_provisioning`` therefore hid the Requeue button, and
    ``operator_requeue_provisioning`` actively raised "Portal is already ready".

THE TRI-STATE CONTRACT (the trap this seals)
--------------------------------------------
The obvious implementation is a loaded gun.
``schema_provisioning_repository.schema_exists`` returns **False** on any
non-PostgreSQL connection — it is a "no-op ⇒ False" helper, not an answer. A
naive ``if not schema_exists(...)`` guard in the settled predicate would
therefore declare EVERY school unprovisioned under RLS mode / SQLite (the whole
local + test topology) and unleash exactly the re-provision storm the watchdog
work just closed.

So this returns THREE states, and the distinction is load-bearing:

  ``True``   the workspace is provably present
  ``False``  the workspace is provably ABSENT (schema mode + no schema anywhere)
  ``None``   UNKNOWABLE — there is no per-tenant schema to probe (RLS mode,
             non-PostgreSQL), so absence proves nothing

Callers MUST treat ``None`` as "no evidence" and fall back to the legacy
assumption. Only a hard ``False`` may downgrade a school. That keeps the fix
inert everywhere except the one topology that can actually answer the question
(``USE_DJANGO_TENANTS=1`` on PostgreSQL — production).
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "rmc:tenant-workspace-exists"


def workspace_probe_cache_seconds() -> int:
    """TTL for a cached workspace probe. Env/settings overridable (no hardcoding).

    The probe is one indexed catalog lookup, but ``resolve_portal_ready`` runs on
    every owner progress poll, so a short cache keeps a marker-less legacy school
    from paying a query per tick. Kept short because a ``False`` flips to ``True``
    the moment a resume lands the schema, and a healer must see that promptly.
    """
    from django.conf import settings

    raw = getattr(settings, "TENANT_WORKSPACE_PROBE_CACHE_SECONDS", None)
    try:
        value = int(raw) if raw is not None else 60
    except (TypeError, ValueError):
        value = 60
    return max(0, value)


def _schema_mode_active() -> bool:
    """True only when tenant schemas are a real, probeable thing on this DB."""
    from django.db import connection

    try:
        from apps.schools.domain_sync import use_django_tenants
    except ImportError:
        return False
    return bool(use_django_tenants()) and connection.vendor == "postgresql"


def _candidate_schema_names(school) -> list[str]:
    """Every schema name this school could legitimately live under.

    Checks the bound ``Client`` row first (authoritative), then the computed
    ``s_<uuid-hex>`` name, then the legacy slug-derived name that earlier
    platform versions used. Absence must mean absence under EVERY naming scheme
    the tree has ever produced, or a genuinely-provisioned legacy tenant would be
    misread as a husk and re-driven.
    """
    names: list[str] = []

    def _add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)

    try:
        from apps.customers.models import Client

        # tenant-isolation-allow: workspace-existence-probe-client-lookup-by-school-fk
        client = Client.objects.filter(school=school).only("schema_name").first()
        if client is not None:
            _add(getattr(client, "schema_name", ""))
    except Exception:  # noqa: BLE001 — a probe must never raise into a progress poll
        logger.debug("tenant_workspace: client lookup failed", exc_info=True)

    try:
        from apps.schools.domain_sync import _schema_name_for_school

        _add(_schema_name_for_school(school))
    except Exception:  # noqa: BLE001
        logger.debug("tenant_workspace: schema-name derivation failed", exc_info=True)

    legacy = (getattr(school, "slug", "") or "").strip().lower().replace("-", "_")
    _add(legacy[:63])

    return names


def _workspace_migration_coverage_floor() -> float:
    """Fraction of expected tenant migrations a schema must have applied to count
    as at HEAD. Below 1.0 so the brief post-deploy window (before
    ``migrate_schemas`` catches every tenant up to a newly-added migration) never
    turns a healthy tenant into a false "absent"; above 0.5 so an early-death
    partial migrate cannot sneak through. Env/settings overridable (no hardcoding).
    """
    from django.conf import settings

    raw = getattr(settings, "TENANT_WORKSPACE_MIGRATION_COVERAGE_FLOOR", None)
    try:
        value = float(raw) if raw is not None else 0.9
    except (TypeError, ValueError):
        value = 0.9
    return min(0.99, max(0.5, value))


def _expected_tenant_migrations() -> set:
    """The ``(app_label, migration_name)`` set a fully-migrated tenant schema
    carries — the live migration graph filtered to ``TENANT_APPS``. Empty when it
    cannot be resolved, which ``_coverage_is_at_head`` reads as "no evidence"
    (never a false "behind").
    """
    try:
        from django.apps import apps as django_apps
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        tenant_names = set(getattr(settings, "TENANT_APPS", []) or [])
        if not tenant_names:
            return set()
        tenant_labels = {
            cfg.label
            for cfg in django_apps.get_app_configs()
            if cfg.name in tenant_names
        }
        if not tenant_labels:
            return set()
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        return {
            (app_label, name)
            for (app_label, name) in loader.graph.nodes
            if app_label in tenant_labels
        }
    except Exception:  # noqa: BLE001 — an unresolvable expectation is "no evidence"
        logger.debug(
            "tenant_workspace: expected-migration set unresolved", exc_info=True
        )
        return set()


def _coverage_is_at_head(applied, expected, floor: float) -> bool:
    """Pure coverage decision (unit-testable without a DB): the schema is at HEAD
    when it has applied at least ``floor`` of the expected tenant migrations. An
    empty ``expected`` means we cannot judge, so we do NOT declare it behind.
    """
    expected = set(expected)
    if not expected:
        return True
    covered = len(set(applied) & expected) / len(expected)
    return covered >= floor


def _schema_is_at_head(schema_name: str) -> bool:
    """True when this schema is migrated to HEAD — not merely "has some table".

    "Has at least one table" cannot tell a healthy tenant from a HALF-migrated
    one: a migrate killed mid-run (the exact failure the watchdog exists for)
    leaves SOME tables and a partial ``django_migrations``, which then reads
    "present" -> "ready" while surfaces whose tables never landed still 500. And
    a bare ``CREATE SCHEMA IF NOT EXISTS`` (customers ``0003``) with no
    ``migrate_schemas --tenant`` leaves an EMPTY schema. This compares the
    schema's applied tenant-migration set against the code's expected set
    (``_expected_tenant_migrations``) and requires substantial coverage.

    Biased hard toward "present": an EMPTY schema (no tables) is provably absent,
    but ANY uncertainty in judging coverage — no ``django_migrations`` ledger, an
    unreadable ledger, an unresolvable expected set — falls back to the old
    "has tables" = present answer. Only a schema PROVABLY below the coverage floor
    is downgraded, so a healthy or merely-post-deploy-behind tenant is never
    turned into a false "absent" that would re-provision it.

    Cross-schema catalog reads only (no schema switching); the schema name is
    quoted, never interpolated raw.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s LIMIT 1",
            [schema_name],
        )
        if cursor.fetchone() is None:
            return False  # empty schema — provably not a workspace
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'django_migrations' LIMIT 1",
            [schema_name],
        )
        if cursor.fetchone() is None:
            # Tables but no migration ledger — cannot judge coverage. Keep the
            # legacy "has tables" = present answer rather than risk a false absent.
            return True
        quoted = connection.ops.quote_name(schema_name)
        cursor.execute("SELECT app, name FROM %s.django_migrations" % quoted)
        applied = {(row[0], row[1]) for row in cursor.fetchall()}

    return _coverage_is_at_head(
        applied, _expected_tenant_migrations(), _workspace_migration_coverage_floor()
    )


def _probe(school) -> bool | None:
    if not _schema_mode_active():
        return None
    names = _candidate_schema_names(school)
    if not names:
        return None
    try:
        for name in names:
            if _schema_is_at_head(name):
                return True
        return False
    except Exception:  # noqa: BLE001 — an unanswerable probe is None, never False
        logger.debug("tenant_workspace: schema probe failed", exc_info=True)
        return None


def tenant_workspace_exists(school, *, use_cache: bool = True) -> bool | None:
    """Tri-state: True = workspace present, False = provably absent, None = unknowable.

    See the module docstring: ``None`` is NOT a synonym for ``False``. A caller
    that collapses them will treat every RLS-mode / SQLite school as a husk.
    """
    if school is None:
        return None
    school_id = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
    if not school_id:
        return None

    ttl = workspace_probe_cache_seconds()
    key = f"{_CACHE_PREFIX}:{school_id}"
    if use_cache and ttl:
        cached = cache.get(key)
        if cached is not None:
            # Cached as a string so a False is distinguishable from a cache miss.
            if cached == "yes":
                return True
            if cached == "no":
                return False
            return None

    result = _probe(school)
    if use_cache and ttl and result is not None:
        cache.set(key, "yes" if result else "no", timeout=ttl)
    return result


def forget_workspace_probe(school) -> None:
    """Drop the cached probe — call after provisioning creates/destroys a schema."""
    school_id = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
    if school_id:
        cache.delete(f"{_CACHE_PREFIX}:{school_id}")
