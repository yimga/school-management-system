"""Is this deployment's database schema actually current?

A box that has pulled new application code but has not run ``migrate`` is the single most
confusing state the platform can be in. Nothing announces it. The box simply starts
throwing ``OperationalError: no such column: <the column the new code reads>`` from
whichever page happens to touch the new field first — reported to the operator as a bare
500 on, say, the backend dashboard, with no hint that the cause is a pending migration.
That is exactly the failure photographed on 2026-08-19 (``academics_academicyear
.is_soft_closed`` on a box two migrations behind), and it is the local half of the
schema-skew gap catalogued as G4 in ``docs/EDGE_SYNC_UPGRADE_BRIEF.md``.

It matters doubly for sync. An inbound bundle carries whatever columns the CLOUD's
registry declares, so a box behind on migrations cannot apply those rows at all — and
before this module the resulting ``OperationalError`` was not in the per-row handler's
except tuple, so it escaped and took the whole bundle down, wedging the cycle in exactly
the way the referential-integrity fix had just closed for foreign keys.

Cheap by construction: the answer is cached, because building the migration graph is far
too expensive to do per request, and it only changes when someone deploys.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_CACHE_KEY = "rmc:sync_engine:schema_guard:pending"
_TTL_SECONDS = 120  # magic-number-allow: schema-drift check cache (seconds)
_MAX_NAMES = 25  # magic-number-allow: pending migrations listed before truncating


def _cache():
    from django.core.cache import cache

    return cache


def pending_migrations(*, force: bool = False) -> list[str]:
    """``["app.0083_name", ...]`` for every migration not yet applied here.

    Empty list means the schema is current. Returns empty on ANY failure too — this is a
    diagnostic, and a diagnostic that can raise is worse than no diagnostic at all. The
    distinction between "current" and "could not tell" is available via :func:`summary`.
    """
    if not force:
        try:
            cached = _cache().get(_CACHE_KEY)
        except Exception:  # noqa: BLE001
            cached = None
        if isinstance(cached, list):
            return list(cached)

    names: list[str] = []
    try:
        from django.db import DEFAULT_DB_ALIAS, connections
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        targets = executor.loader.graph.leaf_nodes()
        for migration, _backwards in executor.migration_plan(targets):
            names.append(f"{migration.app_label}.{migration.name}")
    except Exception:  # noqa: BLE001 — never let the check itself break a page or a cycle
        logger.debug("schema_guard could not compute the migration plan", exc_info=True)
        return []

    try:
        _cache().set(_CACHE_KEY, names, _TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return names


def schema_is_current(*, force: bool = False) -> bool:
    return not pending_migrations(force=force)


def summary(*, force: bool = False) -> dict:
    """Status-surface shape: is the schema current, and if not, what is outstanding."""
    names = pending_migrations(force=force)
    return {
        "current": not names,
        "pending_count": len(names),
        # Truncated: an operator needs to know THAT they are behind and roughly by what,
        # not to read a hundred migration names in a JSON poll.
        "pending": names[:_MAX_NAMES],
        "truncated": len(names) > _MAX_NAMES,
        "checked_at": time.time(),
    }


def drift_note() -> str:
    """One operator-readable sentence, or "" when the schema is current.

    Deliberately names the remedy. "2 migrations behind" sends someone to Slack; "run
    python manage.py migrate" sends them to the fix.
    """
    names = pending_migrations()
    if not names:
        return ""
    head = ", ".join(names[:3])
    more = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
    return (
        f"this deployment is {len(names)} migration(s) behind its code: {head}{more}; "
        "run `python manage.py migrate` on this box"
    )


def reset() -> None:
    """Forget the cached answer — used by tests and right after a deploy/migrate."""
    try:
        _cache().delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "drift_note",
    "pending_migrations",
    "reset",
    "schema_is_current",
    "summary",
]
