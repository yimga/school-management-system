"""
SQLite database recovery: integrity check (PRAGMA).
§2.4 raw_sql_replacement_targets: single place for recover_database command; staff/operational only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import sqlite3

# Reject absurd path strings before sqlite3 URI connect (defense in depth vs runaway paths).
_MAX_SQLITE_INTEGRITY_DB_PATH_LEN = 4096
# Avoid indefinite blocking when another connection holds a lock on the DB file.
_SQLITE_INTEGRITY_CONNECT_TIMEOUT_SEC = 5.0
# Cap PRAGMA integrity_check message size (corrupted DBs can return many fault lines).
_MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN = 8192


def run_sqlite_integrity_check(db_path: Path | str | bytes | None) -> Optional[str]:
    """
    Run PRAGMA integrity_check on the SQLite database at db_path.
    Returns 'ok' if integrity passed, the error string from SQLite if corrupted (clipped to
    _MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN / 8192 chars), or None on I/O/connection error.
    Accepts Path or str only (bytes, bytearray, memoryview, or other types return None without connecting).
    Stripped strings, Path string forms, and resolved paths must not exceed
    _MAX_SQLITE_INTEGRITY_DB_PATH_LEN (4096).
    Uses sqlite3 connect timeout _SQLITE_INTEGRITY_CONNECT_TIMEOUT_SEC (5 seconds).
    """
    if db_path is None:
        return None
    if isinstance(db_path, (bytes, bytearray, memoryview)):
        return None
    if isinstance(db_path, Path):
        path = db_path
        if len(str(path)) > _MAX_SQLITE_INTEGRITY_DB_PATH_LEN:
            return None
    elif isinstance(db_path, str):
        s = db_path.strip()
        if not s:
            return None
        if len(s) > _MAX_SQLITE_INTEGRITY_DB_PATH_LEN:
            return None
        path = Path(s)
    else:
        return None
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return None
    if len(str(resolved)) > _MAX_SQLITE_INTEGRITY_DB_PATH_LEN:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    try:
        conn = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro",
            uri=True,
            timeout=_SQLITE_INTEGRITY_CONNECT_TIMEOUT_SEC,
        )
        try:
            cursor = conn.cursor()
            result = cursor.execute("PRAGMA integrity_check;").fetchone()
            if not result:
                return None
            raw = result[0]
            if not isinstance(raw, str):
                return None
            if len(raw) > _MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN:
                return raw[:_MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN]
            return raw
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None
