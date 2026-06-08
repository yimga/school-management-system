"""Shared SQLite test DB path for gate subprocess bundles (Windows lock-safe)."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_DEFAULT_LOCK_TIMEOUT_SECONDS = 1800.0
_DEFAULT_STALE_LOCK_SECONDS = 21600.0


def sqlite_sidecars_busy(db_path: Path) -> bool:
    return any(db_path.parent.joinpath(f"{db_path.name}{suffix}").exists() for suffix in _SIDECAR_SUFFIXES)


def sqlite_gate_lock_path(db_path: Path) -> Path:
    return db_path.parent / f".{db_path.name}.gate-lock"


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_owner(lock_path: Path) -> dict:
    try:
        return json.loads((lock_path / "owner.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}


def _remove_lock(lock_path: Path, *, expected_token: str | None = None) -> bool:
    owner = _read_lock_owner(lock_path)
    if expected_token and owner.get("token") != expected_token:
        return False
    try:
        (lock_path / "owner.json").unlink(missing_ok=True)
        lock_path.rmdir()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _reap_stale_lock(lock_path: Path, *, stale_after: float) -> bool:
    owner = _read_lock_owner(lock_path)
    try:
        age = max(0.0, time.time() - float(owner.get("created_at", 0)))
    except (TypeError, ValueError):
        age = stale_after + 1
    try:
        pid = int(owner.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    if age <= stale_after and _pid_is_alive(pid):
        return False
    return _remove_lock(lock_path)


@contextmanager
def sqlite_gate_lease(
    db_path: Path,
    *,
    timeout: float | None = None,
    stale_after: float | None = None,
):
    """Hold an interprocess lease for one SQLite test database."""
    timeout = (
        float(os.environ.get("RMC_SQLITE_GATE_LOCK_TIMEOUT_SECONDS", _DEFAULT_LOCK_TIMEOUT_SECONDS))
        if timeout is None
        else timeout
    )
    stale_after = (
        float(os.environ.get("RMC_SQLITE_GATE_STALE_LOCK_SECONDS", _DEFAULT_STALE_LOCK_SECONDS))
        if stale_after is None
        else stale_after
    )
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = sqlite_gate_lock_path(db_path)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + max(0.0, timeout)

    while True:
        try:
            lock_path.mkdir()
            (lock_path / "owner.json").write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "created_at": time.time(),
                        "token": token,
                        "database": str(db_path),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            break
        except FileExistsError:
            if _reap_stale_lock(lock_path, stale_after=stale_after):
                continue
            if time.monotonic() >= deadline:
                owner = _read_lock_owner(lock_path)
                raise TimeoutError(
                    f"Timed out waiting for SQLite gate lease {lock_path}; owner={owner}"
                )
            time.sleep(0.2)

    try:
        yield db_path
    finally:
        _remove_lock(lock_path, expected_token=token)


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
        path = tdir / f"gate_{label}_{os.getpid()}_{time.time_ns()}.sqlite3"
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
