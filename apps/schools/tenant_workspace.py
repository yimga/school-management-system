"""Does this tenant's workspace actually EXIST? — the ground-truth probe.

WHY THIS EXISTS
---------------
``School.is_active`` defaults to ``True`` (``schools.models.School``), so ANY
``School.objects.create(...)`` that skips the provisioning pipeline lands "live"
with no tenant workspace behind it and 500s on every request.

That is not hypothetical, and it is not a one-off: the migration
``schools/0012_seed_default_gilead_school`` MANUFACTURES one on every deploy. It
is a single-tenant-era leftover ("Seed default tenant … one existing tenant")
that creates ``gilead-school`` with ``is_active=True, is_approved=True`` and
never provisions it. Its partner ``customers/0003_ensure_gilead_tenant_domain``
then runs a bare ``CREATE SCHEMA IF NOT EXISTS gilead_school`` with no
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


def _schema_has_tables(schema_name: str) -> bool:
    """True when this schema exists AND has been migrated into.

    Existence alone is NOT the question, and answering it that way would have
    made this whole probe useless on the very row it was written for:
    ``customers/0003_ensure_gilead_tenant_domain`` runs a bare
    ``CREATE SCHEMA IF NOT EXISTS gilead_school`` and NOTHING else — no
    ``migrate_schemas --tenant`` — so the default-seeded tenant can own an EMPTY
    schema. An empty schema is not a workspace; every request against it still
    500s. Healthy production tenants carry ~322 tables / ~1196 applied
    migrations, so "has at least one table" cleanly separates the two.

    One parameterized catalog query — no schema switching, no injection surface.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s LIMIT 1",
            [schema_name],
        )
        return cursor.fetchone() is not None


def _probe(school) -> bool | None:
    if not _schema_mode_active():
        return None
    names = _candidate_schema_names(school)
    if not names:
        return None
    try:
        for name in names:
            if _schema_has_tables(name):
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
