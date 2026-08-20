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


# --------------------------------------------------------------------------- #
# G4 - the cross-deployment half: a schema handshake between box and cloud
# --------------------------------------------------------------------------- #
# The local half above answers "is THIS deployment migrated?". It cannot answer the
# question that actually breaks a sync cycle: "is the deployment I am talking to running
# a DIFFERENT schema from mine?" A box a month behind receives rows referencing columns
# it does not have. Those degrade per row now rather than killing the bundle - but the
# box still silently fails to receive whole entities, and nobody is told why.
#
# The handshake is deliberately per-APP rather than a single global version. A box behind
# only on `finance` must still get its attendance: refusing everything because one app is
# stale would take a school offline for a migration it does not need.

_HEADS_CACHE_KEY = "rmc:sync_engine:schema_guard:heads"


def local_migration_heads(app_labels=()) -> dict:
    """``{app_label: newest APPLIED migration name}`` for the given apps.

    The newest APPLIED one, not the newest on disk: what matters to the far side is which
    columns this database actually has. Returns ``{}`` on any failure - the handshake then
    degrades to "unknown", which is treated as compatible, because refusing to sync
    because a diagnostic failed would be worse than the drift it guards against.
    """
    wanted = {str(a).strip() for a in app_labels if str(a).strip()}
    if not wanted:
        return {}
    # Cached like pending_migrations, and for the same reason: the answer only changes
    # when someone runs migrate, and the download endpoint would otherwise issue this
    # query on every single poll of every box.
    cache_key = f"{_HEADS_CACHE_KEY}:{','.join(sorted(wanted))}"
    try:
        cached = _cache().get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)
    except Exception:  # noqa: BLE001
        pass
    try:
        from django.db.migrations.recorder import MigrationRecorder

        heads: dict = {}
        rows = MigrationRecorder.Migration.objects.filter(app__in=sorted(wanted)).values_list(
            "app", "name"
        )
        for app, name in rows:
            current = heads.get(app)
            # Migration names sort lexicographically by their numeric prefix, which is
            # how Django itself orders them on disk.
            if current is None or name > current:
                heads[app] = name
        try:
            _cache().set(cache_key, heads, _TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
        return heads
    except Exception:  # noqa: BLE001 - a handshake must never break a cycle
        logger.debug("could not read local migration heads", exc_info=True)
        return {}


def encode_heads(heads: dict) -> str:
    """``{"academics": "0083_x"}`` -> ``"academics=0083_x"``, sorted and header-safe.

    A compact ``app=name`` list rather than JSON: it rides in an HTTP header, and only
    the apps owning synced entities are ever included, so it stays short and readable in
    a proxy log.
    """
    parts = []
    for app in sorted(heads or {}):
        name = str(heads[app] or "").strip()
        if not name or "=" in app or "," in name:
            continue
        parts.append(f"{app}={name}")
    return ",".join(parts)


def decode_heads(raw: str) -> dict:
    out: dict = {}
    for chunk in str(raw or "").split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        app, _sep, name = chunk.partition("=")
        app, name = app.strip(), name.strip()
        if app and name:
            out[app] = name[:255]
    return out


def compare_heads(peer_heads: dict, local_heads: dict) -> dict:
    """Which apps the PEER is behind / ahead of us on.

    ``{"behind": {app: (peer, local)}, "ahead": {app: (peer, local)}}``. An app the peer
    did not report is absent from both: unknown is treated as compatible on purpose, so a
    sender that predates the handshake keeps working exactly as before.
    """
    behind, ahead = {}, {}
    for app, local_name in (local_heads or {}).items():
        peer_name = (peer_heads or {}).get(app)
        if not peer_name or not local_name:
            continue
        if peer_name < local_name:
            behind[app] = (peer_name, local_name)
        elif peer_name > local_name:
            ahead[app] = (peer_name, local_name)
    return {"behind": behind, "ahead": ahead}


def describe_skew(comparison: dict) -> str:
    """One operator-readable sentence naming the app and both versions, or ""."""
    behind = (comparison or {}).get("behind") or {}
    ahead = (comparison or {}).get("ahead") or {}
    parts = []
    if behind:
        detail = ", ".join(
            f"{app} {peer} < {local}" for app, (peer, local) in sorted(behind.items())
        )
        parts.append(
            f"this box is behind the cloud on {len(behind)} app(s) ({detail}); those "
            "entities were withheld from the bundle - run `python manage.py migrate` here"
        )
    if ahead:
        detail = ", ".join(
            f"{app} {peer} > {local}" for app, (peer, local) in sorted(ahead.items())
        )
        parts.append(
            f"this box is AHEAD of the cloud on {len(ahead)} app(s) ({detail}); the cloud "
            "has not been migrated yet, so some columns cannot be accepted upward"
        )
    return "; ".join(parts)


def reset() -> None:
    """Forget the cached answer — used by tests and right after a deploy/migrate."""
    try:
        _cache().delete(_CACHE_KEY)
        # The heads cache is keyed by the app SET requested, so there is no single key to
        # drop. delete_pattern exists only on some backends; falling back to expiring the
        # one key the platform actually uses (all synced apps) keeps reset() honest for
        # tests without pretending to a guarantee the cache API does not give.
        from apps.api.sync_services import entity_app_labels

        apps_key = ",".join(sorted(set(entity_app_labels().values())))
        _cache().delete(f"{_HEADS_CACHE_KEY}:{apps_key}")
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "compare_heads",
    "decode_heads",
    "describe_skew",
    "drift_note",
    "encode_heads",
    "local_migration_heads",
    "pending_migrations",
    "reset",
    "schema_is_current",
    "summary",
]
