"""Regression guard for the single-schema tenant shim (2026-08-01).

The 2026-07-31 full-platform census had a dominant failure cluster (~168
of 232) of ``AttributeError: 'DatabaseWrapper' object has no attribute
'tenant'`` — code entering django_tenants ``schema_context(schema_name)``
under ``USE_DJANGO_TENANTS=0``, where the plain (non-django_tenants)
backend has no tenant machinery. The failures were ordering-triggered
(they only fired once test ordering left a bundle carrying a populated
``schema_name``), so they never showed in isolation.

``config.reliable_test_runner.ReliableDiscoverRunner`` (the default
``TEST_RUNNER``) now installs ``install_single_schema_tenant_shim()``
before the suite runs, making ``schema_context`` a harmless no-op in
single-schema mode (there is only one schema, so it is semantically a
no-op anyway; row-level scoping is what isolates tenants here).

This test is the must-fire guard: if the runner stops installing the
shim, entering ``schema_context`` raises again and this errors.
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase


class SingleSchemaTenantShimTests(SimpleTestCase):
    def setUp(self) -> None:
        if getattr(settings, "USE_DJANGO_TENANTS", False):
            self.skipTest(
                "shim only applies to single-schema mode (USE_DJANGO_TENANTS=0)"
            )

    def test_schema_context_is_a_noop_and_does_not_raise(self) -> None:
        """Entering schema_context on a populated schema_name must not raise.

        Without the shim this is the exact ``'DatabaseWrapper' object has
        no attribute 'tenant'`` crash from the census.
        """
        from django_tenants.utils import schema_context

        with schema_context("some_nonexistent_tenant_schema"):
            pass  # enter + exit must both be no-ops

    def test_shim_function_is_idempotent(self) -> None:
        """Re-installing the shim is safe (skips already-shimmed backends)."""
        from django.db import connections

        from config.reliable_test_runner import install_single_schema_tenant_shim

        install_single_schema_tenant_shim()
        install_single_schema_tenant_shim()  # second call must not raise
        cls = type(connections["default"])
        self.assertTrue(hasattr(cls, "set_schema"))
        self.assertIsNone(getattr(cls, "tenant"))
