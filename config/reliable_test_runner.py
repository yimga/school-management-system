"""
Serial Django test runner with explicit DB connection cleanup.

- Forces parallel=0 (no multiprocessing test pool).
- Closes all connections before/after the suite to avoid SQLite handle leaks on Windows.
- Installs a single-schema tenant shim so django_tenants ``schema_context``
  is a harmless no-op under ``USE_DJANGO_TENANTS=0`` (see below).

Disable via env: RMC_RELIABLE_TEST_RUNNER=0
"""

from __future__ import annotations

import logging

from django.db import connections
from django.test.runner import DiscoverRunner

logger = logging.getLogger(__name__)


def install_single_schema_tenant_shim() -> list[str]:
    """Make ``django_tenants.utils.schema_context`` a no-op in single-schema mode.

    Under ``USE_DJANGO_TENANTS=0`` (the SQLite test/dev lane, and any RLS
    single-schema deploy) the DB uses a plain, non-django_tenants backend
    whose ``DatabaseWrapper`` has none of ``tenant`` / ``set_schema`` /
    ``set_schema_to_public`` / ``set_tenant``. Any code that enters
    ``schema_context(schema_name)`` on a populated schema then dies with
    ``AttributeError: 'DatabaseWrapper' object has no attribute 'tenant'``.

    There is only ONE schema in this mode, so ``schema_context`` *should*
    be a no-op — the tenant-scoping that matters here is row-level, not
    schema-level. This adds the four missing shims to the configured
    backend class(es) so entering ``schema_context`` is harmless instead of
    a crash. Returns the list of aliases whose backend was patched.

    Safety:

    * No-op when ``USE_DJANGO_TENANTS`` is truthy — production (which sets
      it to 1) uses the real django_tenants backend and is never touched.
    * Skips any backend that already has ``set_schema`` (i.e. the real
      django_tenants backend), so a mixed config can't be clobbered.
    * Installed ONLY by the test runner, so it never runs outside a test
      process.
    """
    from django.conf import settings

    if getattr(settings, "USE_DJANGO_TENANTS", False):
        return []

    patched: list[str] = []
    for alias in connections:
        cls = type(connections[alias])
        if hasattr(cls, "set_schema"):
            # Real django_tenants backend (or already shimmed) — leave it.
            continue
        cls.tenant = None
        cls.set_schema = lambda self, *a, **k: None
        cls.set_schema_to_public = lambda self, *a, **k: None
        cls.set_tenant = lambda self, *a, **k: None
        patched.append(alias)
    if patched:
        logger.debug(
            "single_schema_tenant_shim_installed",
            extra={"aliases": patched},
        )
    return patched


class ReliableDiscoverRunner(DiscoverRunner):
    """DiscoverRunner that always runs tests serially and closes SQLite handles aggressively."""

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        kwargs["parallel"] = 0
        # Make schema_context a no-op under single-schema (USE_DJANGO_TENANTS=0)
        # BEFORE any test imports/enters it, so ordering-dependent bundles that
        # carry a populated schema_name don't crash on the plain backend.
        install_single_schema_tenant_shim()
        connections.close_all()
        try:
            return super().run_tests(test_labels, extra_tests=extra_tests, **kwargs)
        finally:
            connections.close_all()

    def teardown_databases(self, old_config, **kwargs):
        try:
            return super().teardown_databases(old_config, **kwargs)
        finally:
            connections.close_all()
