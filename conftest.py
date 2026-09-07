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


def _pytest_django_active() -> bool:
    """Return True if pytest-django will manage the test DB lifecycle for us.

    When pytest-django is installed AND active, it calls ``setup_databases``
    inside its own session-scoped fixture and blocks raw DB access via a
    ``_blocking_wrapper``. If we ALSO call ``setup_databases`` from this
    conftest we get the "Database access not allowed" RuntimeError on every
    test even though the DB was created. The Wave 9 Agent P fix is to defer
    entirely to pytest-django when it is loaded (i.e. when ``pytest-django``
    is on the path) AND let it run the show via the ``django_db_setup``
    fixture chain. This conftest's bespoke ``setup_databases`` call is kept
    as a fallback for environments that intentionally disable pytest-django
    via ``-p no:django``.
    """
    try:
        import pytest_django  # noqa: F401
        return True
    except ImportError:
        return False


def _using_inmemory_test_settings() -> bool:
    """Return True if DJANGO_SETTINGS_MODULE resolves to in-memory SQLite.

    The in-memory path means there is no file handle for Windows to lock,
    no journal file to detect as 'stale', and no schema cache to reuse —
    so we skip the journal-probe + retry dance entirely.
    """
    from django.conf import settings as django_settings

    default_db = django_settings.DATABASES.get("default") or {}
    if default_db.get("ENGINE") != "django.db.backends.sqlite3":
        return False
    test_name = ((default_db.get("TEST") or {}).get("NAME") or "").strip()
    name = (default_db.get("NAME") or "").strip()
    return test_name == ":memory:" or name == ":memory:"


def _install_test_environment(session) -> None:
    """Mirror the OTHER half of DiscoverRunner.

    ``setup_databases()`` gives a test a database. ``setup_test_environment()``
    is what gives it the test ENVIRONMENT, and they are separate calls:

      * the locmem email backend, which is the only thing that fills
        ``mail.outbox`` -- with the console backend it stays [] forever;
      * the instrumented template renderer, which is the only thing that
        populates ``response.context`` -- without it the attribute is None;
      * ``DEBUG = False``, so views take the branch production takes.

    This file called only the first for as long as it has existed. Measured on
    2026-09-01 with a probe, before the fix:

        EMAIL_BACKEND=...console.EmailBackend | DEBUG=True
        outbox_len_after_send=0 | response_context_is_none=True

    So under pytest every ``len(mail.outbox)`` assertion measured a list
    nothing could fill, and every ``response.context[...]`` lookup ran against
    None. 19 test modules assert on the outbox and 14 on the context. Under
    ``manage.py test`` the same assertions work, because DiscoverRunner makes
    both calls -- which is exactly why the gap survived: the runner CI uses for
    most suites was never the runner that could see it.

    Not called when pytest-django is active: it installs the same environment
    from its own ``django_test_environment`` fixture, and a second call raises
    RuntimeError rather than being ignored.
    """
    from django.test.utils import setup_test_environment

    # debug=False EXPLICITLY. The default is not False, it is
    # settings.DEBUG -- so a bare setup_test_environment() leaves DEBUG at
    # whatever the settings module chose and the suite runs views down the
    # development branch. DiscoverRunner passes debug=self.debug_mode, which
    # is False; passing it here is what makes the two runners agree.
    setup_test_environment(debug=False)
    session._django_test_environment = True


def _restore_test_environment(session) -> None:
    if not getattr(session, "_django_test_environment", False):
        return
    from django.test.utils import teardown_test_environment

    teardown_test_environment()
    session._django_test_environment = False


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


def _seed_fingerprint_gate(session) -> None:
    """Fingerprint a freshly built test DB, or refuse a damaged reused one.

    The flush damage is permanent and invisible: a data migration recorded as
    applied never re-seeds, so a truncated catalog stays truncated for every
    later run of that file. Measured cost on five known-red files: 21 failures
    against 4. Every one of the 17 read as a code regression, and some tests
    PASS on a damaged DB only because a request is refused before reaching the
    assertion. So the database has to say so itself, before any test runs.
    """
    if _using_inmemory_test_settings():
        return
    try:
        from django.db import connections

        from apps.test_utils import seed_fingerprint
    except Exception:
        # Never let the guard be the reason a suite cannot start.
        return

    try:
        connection = connections["default"]
        if not getattr(session, "_django_db_keepdb", False):
            # Built this session, so its state is known-good by construction.
            seed_fingerprint.record(connection)
            return
        damaged = seed_fingerprint.damaged_tables(connection)
    except Exception as exc:  # noqa: BLE001
        print(
            "[pytest bootstrap] seed fingerprint check skipped: %s" % exc,
            file=sys.stderr,
        )
        return

    if damaged is None:
        # "Unknown" is not "clean". This DB predates the guard, so say so rather
        # than let a silent pass read as a verified one.
        print(
            "[pytest bootstrap] NOTICE: this reused test database has no seed "
            "fingerprint, so its integrity is unverified. One rebuild "
            "establishes the baseline and every later run is checked.",
            file=sys.stderr,
        )
        return
    if not damaged:
        return

    print(
        seed_fingerprint.report(
            damaged, str(connection.settings_dict.get("NAME") or "?")
        ),
        file=sys.stderr,
    )
    if seed_fingerprint.escape_hatch_engaged():
        print(
            "[pytest bootstrap] %s is set; continuing against a damaged database."
            % seed_fingerprint.ESCAPE_ENV,
            file=sys.stderr,
        )
        return
    import pytest

    pytest.exit(
        "test database is damaged (%d seeded table(s) empty); see above"
        % len(damaged),
        returncode=1,
    )


def pytest_sessionstart(session) -> None:
    """Mirror DiscoverRunner: point default connection at TEST database.

    Defers entirely to pytest-django when present (Wave 9 Agent P fix);
    skips journal-probe retry when in-memory SQLite is configured.
    """
    if _pytest_django_active():
        # pytest-django will call setup_databases() from its own fixture
        # chain. Recording nothing on the session keeps pytest_sessionfinish
        # a no-op so we don't double-teardown.
        return

    from django.apps import apps
    from django.test.utils import setup_databases

    if not apps.ready:
        return

    # Before setup_databases, as DiscoverRunner does it.
    _install_test_environment(session)

    if _using_inmemory_test_settings():
        # In-memory SQLite: no journal probe, no retry. Just create.
        session._django_db_keepdb = False
        session._django_db_old_config = setup_databases(
            verbosity=1,
            interactive=False,
            keepdb=False,
        )
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
        _seed_fingerprint_gate(session)
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
        _seed_fingerprint_gate(session)


def pytest_sessionfinish(session, exitstatus) -> None:
    _restore_test_environment(session)
    cfg = getattr(session, "_django_db_old_config", None)
    if cfg is None:
        return
    from django.test.utils import teardown_databases

    keepdb = getattr(session, "_django_db_keepdb", _pytest_keepdb_enabled())
    teardown_databases(cfg, verbosity=1, parallel=0, keepdb=keepdb)
    try:
        from django.db import connections

        connections.close_all()
    except Exception:
        pass
