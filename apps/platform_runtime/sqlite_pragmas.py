"""
SQLite connection pragmas — WAL + sane sync for file-backed DBs (tests, local dev).

Reduces intermittent ``database is locked`` when many writers share one test file
(--keepdb on Windows). Safe no-op for in-memory databases.
"""

from __future__ import annotations

import logging

from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)

def _apply_sqlite_pragmas(sender, connection, **kwargs) -> None:
    if connection.vendor != "sqlite":
        return
    db_name = connection.settings_dict.get("NAME") or ""
    if db_name == ":memory:":
        return
    try:
        with connection.cursor() as cursor:
            # Busy timeout is set via DATABASES OPTIONS; WAL reduces writer lock contention.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        logger.debug("SQLite PRAGMA setup skipped", exc_info=True)


def connect_sqlite_pragma_signal() -> None:
    connection_created.connect(
        _apply_sqlite_pragmas,
        weak=False,
        dispatch_uid="platform_runtime.apply_sqlite_pragmas",
    )


__all__ = ["connect_sqlite_pragma_signal"]
