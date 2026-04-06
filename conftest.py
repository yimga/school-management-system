"""
Pytest bootstrap: configure Django so tests can use settings, URLs, and static().

CI and local runs use `pytest` without requiring pytest-django.

**SQLite test DB:** `setup_databases` uses a file under `.django_test_dbs/` (see Django test settings).
`PYTEST_KEEPDB` defaults to `1` (reuse). If the reused sqlite file is stale or half-migrated,
pytest retries once on a fresh unique file so broad bundles do not die during session start.
See `docs/BATCH_14_DYNAMICFIELD_RECONCILIATION.md` §5.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path


def _pytest_keepdb_enabled() -> bool:
    return os.environ.get("PYTEST_KEEPDB", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _should_retry_sqlite_keepdb(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "already exists",
            "no such table",
            "database is locked",
            "disk image is malformed",
        )
    )


def _fresh_pytest_sqlite_db_path() -> Path:
    db_dir = Path(__file__).resolve().parent / ".django_test_dbs"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / f"pytest_retry_{os.getpid()}_{uuid.uuid4().hex}.sqlite3"


def _retarget_sqlite_test_databases(db_path: Path) -> None:
    from django.conf import settings as django_settings
    from django.db import connections

    resolved = str(db_path.resolve())
    os.environ["DJANGO_TEST_DB_FILE"] = resolved
    for alias, db_config in django_settings.DATABASES.items():
        if db_config.get("ENGINE") != "django.db.backends.sqlite3":
            continue
        db_config.setdefault("TEST", {})
        db_config["TEST"]["NAME"] = resolved
        if alias in connections:
            connections[alias].close()
            connections[alias].settings_dict.setdefault("TEST", {})
            connections[alias].settings_dict["TEST"]["NAME"] = resolved


def _is_default_sqlite_test_db() -> bool:
    from django.conf import settings as django_settings

    default_db = django_settings.DATABASES.get("default") or {}
    if default_db.get("ENGINE") != "django.db.backends.sqlite3":
        return False
    test_name = ((default_db.get("TEST") or {}).get("NAME") or "").replace("\\", "/")
    return test_name.endswith(".django_test_dbs/default.sqlite3")


def _default_sqlite_test_db_path() -> Path | None:
    from django.conf import settings as django_settings

    default_db = django_settings.DATABASES.get("default") or {}
    if default_db.get("ENGINE") != "django.db.backends.sqlite3":
        return None
    test_name = (default_db.get("TEST") or {}).get("NAME")
    if not test_name:
        return None
    return Path(test_name).resolve()


def _sqlite_keepdb_needs_fresh_start() -> bool:
    db_path = _default_sqlite_test_db_path()
    if db_path is None:
        return False
    return any(
        db_path.parent.joinpath(f"{db_path.name}{suffix}").exists()
        for suffix in ("-journal", "-wal", "-shm")
    )


def pytest_configure() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.apps import apps

    # Avoid double setup if another plugin or test module initialized Django first.
    if apps.ready:
        return
    django.setup()

    # Reduce flaky "database is locked" under parallel pytest / slow disks (SQLite default is 5s).
    from django.conf import settings as django_settings

    default_db = django_settings.DATABASES.get("default") or {}
    if "sqlite" in str(default_db.get("ENGINE", "")):
        opts = default_db.setdefault("OPTIONS", {})
        opts.setdefault("timeout", 30)


def pytest_sessionstart(session) -> None:
    """Mirror DiscoverRunner: point default connection at TEST database (file-backed sqlite)."""
    from django.apps import apps
    from django.test.utils import setup_databases

    if not apps.ready:
        return
    keepdb = _pytest_keepdb_enabled()
    if keepdb and _is_default_sqlite_test_db() and _sqlite_keepdb_needs_fresh_start():
        retry_db = _fresh_pytest_sqlite_db_path()
        print(
            "[pytest bootstrap] sqlite keepdb journal detected; using fresh DB "
            f"{retry_db.name} for this run.",
            file=sys.stderr,
        )
        _retarget_sqlite_test_databases(retry_db)
        keepdb = False
    session._django_db_keepdb = keepdb
    try:
        session._django_db_old_config = setup_databases(
            verbosity=1,
            interactive=False,
            keepdb=keepdb,
        )
    except Exception as exc:
        if not (
            keepdb
            and _is_default_sqlite_test_db()
            and _should_retry_sqlite_keepdb(exc)
        ):
            raise
        retry_db = _fresh_pytest_sqlite_db_path()
        print(
            "[pytest bootstrap] keepdb sqlite setup failed; retrying once on fresh DB "
            f"{retry_db.name}: {exc}",
            file=sys.stderr,
        )
        _retarget_sqlite_test_databases(retry_db)
        session._django_db_keepdb = False
        session._django_db_old_config = setup_databases(
            verbosity=1,
            interactive=False,
            keepdb=False,
        )


def pytest_sessionfinish(session, exitstatus) -> None:
    cfg = getattr(session, "_django_db_old_config", None)
    if cfg is None:
        return
    from django.test.utils import teardown_databases

    keepdb = getattr(session, "_django_db_keepdb", _pytest_keepdb_enabled())
    teardown_databases(cfg, verbosity=1, parallel=0, keepdb=keepdb)
