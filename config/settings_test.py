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
# defensively even though they don't write to it, and the border-lock tests
# reference the regional aliases under @override_settings. They exist so a
# `using="preview"` call doesn't trip a KeyError mid-test -- nothing more.
#
# THEY MUST DECLARE TEST["MIRROR"], and a bare `.copy()` is not that.
#
# `setup_databases` creates and MIGRATES every alias that is not a mirror. A
# plain copy therefore made these independent databases, so the full migration
# chain ran once per alias -- and the second pass replayed migrations whose
# historical field sets no longer match the table the first pass had already
# built and populated. It died in siteconfig/0004 with
# `UNIQUE constraint failed: siteconfig_themepack.is_default` (0076 had by then
# added the one-default partial index and moved the default onto another pack),
# and immediately after with
# `NOT NULL constraint failed: siteconfig_themepack.logo_background_mode`
# (a column added by a later migration that 0004's historical model cannot know
# to populate). Fixing those one at a time is whack-a-mole: replaying a
# migration chain over an already-migrated database is unsound in general.
#
# The cost was total and silent: test-database creation aborts, so pytest exits
# 3 (INTERNALERROR) and NOT ONE TEST RUNS -- in any app. A suite that cannot
# start looks exactly like a suite that passes unless somebody reads the exit
# code, and `pytest | tail` reports the pipe's status, not pytest's.
#
# MIRROR is precisely the "same data as default, do not create or migrate it"
# declaration Django provides for read replicas, which is what these are. Each
# needs its OWN TEST dict: `.copy()` is shallow, so the copies share default's.
def _mirror_of_default() -> dict:
    alias = DATABASES["default"].copy()
    alias["TEST"] = {**DATABASES["default"].get("TEST", {}), "MIRROR": "default"}
    return alias


DATABASES["preview"] = _mirror_of_default()
DATABASES["replica_eu_central"] = _mirror_of_default()
DATABASES["replica_us_east"] = _mirror_of_default()

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

# Silence the noisy structured logger during tests.
#
# LOGGING_CONFIG = None tells Django not to configure logging at all, so the
# rotating file handler in config.settings never attaches -- which also stops
# concurrent test runners fighting over logs/django.log. A NullHandler on the
# root swallows whatever is still emitted.
#
# This deliberately does NOT call logging.disable(). It used to, and the comment
# beside it claimed "individual tests that need to assert on log output use
# assertLogs() which installs its own handler" -- which is not how
# logging.disable works. It short-circuits inside Logger.isEnabledFor BEFORE any
# handler is consulted, so it defeats assertLogs too. 115 assertLogs assertions
# across 52 test modules were silently unrunnable under these settings, among
# them the seals proving the password-rotation writer never logs a raw secret
# and that a soft-mode residency mismatch warns instead of raising. Those tests
# did not fail loudly -- they failed with "no logs of level INFO or higher",
# which reads like a product bug and is not one.
#
# CI runs config.settings, so this only ever bit local runs -- which is worse,
# not better: the guards were absent from exactly the runs people iterate on.
LOGGING_CONFIG = None
import logging  # noqa: E402

_root_logger = logging.getLogger()
_root_logger.handlers = [logging.NullHandler()]
_root_logger.setLevel(logging.WARNING)

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
