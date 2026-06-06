"""Shared SQLite test DB path for gate subprocess bundles (Windows lock-safe)."""

from __future__ import annotations

import os
import time
from pathlib import Path

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def sqlite_sidecars_busy(db_path: Path) -> bool:
    return any(db_path.parent.joinpath(f"{db_path.name}{suffix}").exists() for suffix in _SIDECAR_SUFFIXES)


def gate_session_marker(root: Path, session: str) -> Path:
    return root / ".django_test_dbs" / f"gate_session_{session}.path"


def read_gate_session_db(root: Path) -> Path | None:
    session = os.environ.get("RMC_SQLITE_GATE_SESSION", "").strip()
    if not session:
        return None
    marker = gate_session_marker(root, session)
    if not marker.is_file():
        return None
    raw = marker.read_text(encoding="utf-8").strip()
    return Path(raw) if raw else None


def write_gate_session_db(root: Path, session: str, db_path: Path) -> None:
    marker = gate_session_marker(root, session)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(db_path.resolve()), encoding="utf-8")


def ensure_gate_session(root: Path, *, force_fresh: bool = False) -> Path:
    """Return a file-backed test DB for the current gate session.

    When ``RMC_SQLITE_GATE_SESSION`` is set, all subprocesses in one sweep share
    the same path (written to ``.django_test_dbs/gate_session_<id>.path``).
    Falls back to stable ``rmc_sqlite_test_runner.sqlite3`` unless sidecars
    indicate another process holds the file — then allocates a timestamped gate DB.
    """
    explicit = (os.environ.get("DJANGO_TEST_DB_FILE") or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = root / path
        return path.resolve()

    session = os.environ.get("RMC_SQLITE_GATE_SESSION", "").strip()
    existing = read_gate_session_db(root)
    if existing and existing.is_file() and not force_fresh:
        return existing

    tdir = root / ".django_test_dbs"
    tdir.mkdir(parents=True, exist_ok=True)
    stable = tdir / "rmc_sqlite_test_runner.sqlite3"

    if force_fresh or sqlite_sidecars_busy(stable):
        label = session or "fresh"
        path = tdir / f"gate_{label}_{int(time.time())}.sqlite3"
    else:
        path = stable

    if session:
        write_gate_session_db(root, session, path)
    return path.resolve()


def bootstrap_gate_session_env(root: Path, *, session_id: str | None = None, force_fresh: bool = False) -> Path:
    """Initialize env for a multi-step gate sweep; returns resolved test DB path."""
    if not os.environ.get("RMC_SQLITE_GATE_SESSION", "").strip():
        os.environ["RMC_SQLITE_GATE_SESSION"] = session_id or f"gate_{int(time.time())}"
    db_path = ensure_gate_session(root, force_fresh=force_fresh)
    os.environ["DJANGO_TEST_DB_FILE"] = str(db_path)
    os.environ.setdefault("PYTEST_KEEPDB", "1")
    return db_path
