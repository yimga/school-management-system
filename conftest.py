"""
Pytest bootstrap: configure Django so tests can use settings, URLs, and static().

CI and local runs use `pytest` without requiring pytest-django.

**SQLite test DB:** `setup_databases` uses a file under `.django_test_dbs/` (see Django test settings).
`PYTEST_KEEPDB` defaults to `1` (reuse). If migrations moved (e.g. siteconfig DynamicField* retire)
and you see missing-table errors, set `PYTEST_KEEPDB=0` once or delete `.django_test_dbs/default.sqlite3`
after closing handles (especially on Windows). See `docs/BATCH_14_DYNAMICFIELD_RECONCILIATION.md` §5.
"""

from __future__ import annotations

import os


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
    keepdb = os.environ.get("PYTEST_KEEPDB", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    session._django_db_old_config = setup_databases(
        verbosity=1,
        interactive=False,
        keepdb=keepdb,
    )


def pytest_sessionfinish(session, exitstatus) -> None:
    cfg = getattr(session, "_django_db_old_config", None)
    if cfg is None:
        return
    from django.test.utils import teardown_databases

    keepdb = os.environ.get("PYTEST_KEEPDB", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    teardown_databases(cfg, verbosity=1, parallel=0, keepdb=keepdb)
