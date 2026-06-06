"""SQLite concurrency pragmas for local / dev runs.

Production runs on PostgreSQL, where these are no-ops (the handler returns
early for any non-sqlite vendor). On a local file-backed SQLite database the
default rollback journal serializes readers against the single writer, so the
threaded ``runserver`` throws ``OperationalError: database is locked`` whenever
two requests touch the DB at once (e.g. a page that writes during GET while a
favicon / asset request is in flight). That surfaces as flaky 500s under the
visual-QA Playwright sweep even though the view code is correct.

WAL journal mode lets readers run concurrently with the single writer, and a
generous ``busy_timeout`` makes the writer wait for a lock instead of erroring
immediately — together they remove the spurious lock errors. The pragmas are
applied per connection via the ``connection_created`` signal; ``journal_mode``
is database-level and persists, the rest are connection-scoped.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA busy_timeout=30000;",
    "PRAGMA foreign_keys=ON;",
)


def apply_sqlite_pragmas(sender, connection, **kwargs):
    """Apply concurrency-friendly pragmas to new SQLite connections only."""
    if connection.vendor != "sqlite":
        return
    try:
        with connection.cursor() as cursor:
            for pragma in _SQLITE_PRAGMAS:
                cursor.execute(pragma)  # rls-bypass-allow: static SQLite PRAGMA strings (no tenant data / no interpolation), dev concurrency tuning only
    except Exception as exc:  # noqa: BLE001 — pragmas are best-effort dev tuning
        logger.debug("SQLite pragma application skipped: %s", exc)


def connect_sqlite_pragmas():
    """Wire ``apply_sqlite_pragmas`` to the connection_created signal once."""
    from django.db.backends.signals import connection_created

    # weak=False so the module-level handler isn't garbage-collected; dispatch_uid
    # makes the connect idempotent across repeated ready() calls (e.g. autoreload).
    connection_created.connect(
        apply_sqlite_pragmas,
        weak=False,
        dispatch_uid="siteconfig.apply_sqlite_pragmas",
    )
