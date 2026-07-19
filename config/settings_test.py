"""
RunMyCampus test-only settings (Wave 9 Agent P, v3.58.x).

Purpose
-------
Unblock Windows test execution by sidestepping the file-backed SQLite
test database that the documented v3.54.0+ test-DB lock is rooted in.

The lock pattern in `config/settings.py` + `conftest.py` is correct for
Linux CI (file-backed SQLite + `--keepdb` survives across `manage.py test`
invocations) BUT Windows holds file handles across test-class boundaries
and across subprocess exits, so subsequent runs find the file locked OR
the journal/wal files trip the `_sqlite_keepdb_needs_fresh_start()` guard
and force a full 845-migration rebuild every run.

This module pivots to **in-memory SQLite** for tests. The database is
created when the process opens its first cursor and destroyed when the
process exits — no file handle is ever taken on a path that another
process could lock. Subsequent runs always get a clean schema. Per-run
cost is the migration spin-up (~30s-90s depending on machine); per-test
DB transactions are still rolled back by Django's `TestCase` wrapper.

Use this module when:
  * you are on Windows and `manage.py test` or `pytest` is hanging on
    "Using existing test database" / "Destroying old test database",
  * you are on Linux and just want a fast, isolated, single-process
    test run (no shared file-backed cache to worry about),
  * you are wiring a CI matrix job that ALSO needs to catch
    Windows-only regressions (run with this module on a windows-latest
    runner).

Do NOT use this module for:
  * postgres-specific features (Window functions you've extended,
    pgvector, `django-tenants` schemas, JSONField operators that differ
    from sqlite-json1). Those tests stay on the Linux + Postgres CI
    path and carry `@pytest.mark.requires_postgres`.

Activation
----------
PowerShell:    $env:DJANGO_SETTINGS_MODULE = "config.settings_test"
bash / WSL:    export DJANGO_SETTINGS_MODULE=config.settings_test

Or use the helper scripts:
    scripts/run_tests_windows.ps1
    scripts/run_tests.sh

The helper scripts also flip env flags that downstream modules read to
silence noisy I/O during tests (Celery becomes eager, email is locmem,
log handlers are disabled).
"""

from __future__ import annotations

import os

# Mark the test runner BEFORE importing the parent settings, so any
# RUNNING_TESTS branches that depend on env (not just sys.argv) see it.
os.environ.setdefault("RMC_RUNNING_TESTS", "1")
os.environ.setdefault("DJANGO_TEST_INMEMORY", "1")

# Tell the existing config/settings.py SQLite-test branch NOT to take
# the file-backed path. We override DATABASES below anyway, but this
# also short-circuits the `_sqlite_keepdb_needs_fresh_start()` journal
# probe inside conftest.py because the resolved TEST NAME is ":memory:".
os.environ.setdefault("RMC_SQLITE_TEST_MEMORY", "1")
os.environ.setdefault("RMC_SQLITE_TEST_USE_MEMORY_NAME", "1")

# Defensive: any module that reads DATABASE_URL at import time would
# otherwise try to connect to the developer's local Postgres. Force the
# SQLite fallback path inside config/settings.py.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("PREVIEW_DATABASE_URL", None)

from .settings import *  # noqa: E402,F401,F403

# --- DATABASES override ------------------------------------------------
#
# In-memory SQLite. The TEST/NAME=":memory:" pair tells Django's test
# runner to also build the test DB in memory rather than cloning a file
# (which is what triggers the Windows handle lock). CONN_MAX_AGE=0 is
# critical: persistent connections would let the in-memory DB outlive
# its creating thread under threaded test scenarios, then the next
# connection would see an empty schema. 0 = create-and-tear-down per
# request, which matches Django's TestCase atomic-block expectation.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
        "OPTIONS": {"timeout": 30.0},
        "CONN_MAX_AGE": 0,
    },
}

# The schoolops + siteconfig test paths import the `preview` alias
# defensively even though they don't write to it. Mirror default so a
# `using="preview"` call doesn't trip a KeyError mid-test.
DATABASES["preview"] = DATABASES["default"].copy()

# Stub regional aliases so border-lock tests can reference real DATABASES
# entries under @override_settings without touching production config.
DATABASES["replica_eu_central"] = DATABASES["default"].copy()
DATABASES["replica_us_east"] = DATABASES["default"].copy()

# Disable router fan-out during tests. The tenant + preview routers
# add overhead and surface lookup failures that have nothing to do
# with the system under test.
DATABASE_ROUTERS: list[str] = []

# --- Side-effect quiescing ---------------------------------------------
#
# Celery runs in-process so tests don't have to spin up a broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Email lands in locmem.outbox; nothing is sent over SMTP.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Cache is local-mem so test isolation doesn't depend on Redis being up.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "rmc-test-locmem",
    },
}

# Channels (websocket layer) — use in-memory so AI chat tests don't need
# Redis.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Password hasher: MD5 is fast and acceptable for test fixture user
# creation. NEVER use this anywhere outside tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Silence the noisy structured logger during tests. Individual tests
# that need to assert on log output use assertLogs() which installs
# its own handler.
LOGGING_CONFIG = None
import logging  # noqa: E402

logging.disable(logging.CRITICAL)

# Turn off DEBUG to mimic prod-ish behavior; turn off whitenoise template
# serving so staticfiles tests don't depend on collectstatic having run.
DEBUG = False
TEMPLATES_DEBUG = False

# Skip cookies-based session middleware noise.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

# Test files / media — write to a fresh tempdir per session so parallel
# pytest workers don't collide.
import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp(prefix="rmc-test-media-")

# Sentry is a no-op in tests.
SENTRY_DSN = ""
