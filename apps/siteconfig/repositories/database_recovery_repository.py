"""
SQLite database recovery: integrity check (PRAGMA).
§2.4 raw_sql_replacement_targets: single place for recover_database command; staff/operational only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import sqlite3


def run_sqlite_integrity_check(db_path: Path | str) -> Optional[str]:
    """
    Run PRAGMA integrity_check on the SQLite database at db_path.
    Returns 'ok' if integrity passed, the error string from SQLite if corrupted, or None on I/O/connection error.
    """
    path = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(str(path))
        try:
            cursor = conn.cursor()
            result = cursor.execute("PRAGMA integrity_check;").fetchone()
            return result[0] if result else None
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None
