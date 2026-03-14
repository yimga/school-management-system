"""
Contract tests for apps.schools.rls_context (§2.4 RUNMYCAMPUS; NEXT_50 step 45 optional).

Ensures set_rls_school_id / reset_rls_school_id are callable and safe for middleware use:
- No-op on non-PostgreSQL; no raise.
- On PostgreSQL, set then reset does not raise (middleware request/response cycle).
"""
from django.test import TestCase

from apps.schools.rls_context import reset_rls_school_id, set_rls_school_id


class RlsContextContractTests(TestCase):
    """Contract: rls_context helpers used by middleware are callable and safe."""

    def test_set_rls_school_id_callable_no_raise(self):
        """set_rls_school_id(id) does not raise (no-op on non-postgres)."""
        set_rls_school_id(1)
        set_rls_school_id("00000000-0000-0000-0000-000000000001")

    def test_reset_rls_school_id_callable_no_raise(self):
        """reset_rls_school_id() does not raise (no-op on non-postgres)."""
        reset_rls_school_id()

    def test_set_then_reset_cycle_no_raise(self):
        """Middleware-like cycle: set then reset does not raise."""
        set_rls_school_id(99)
        reset_rls_school_id()

    def test_reset_idempotent(self):
        """reset_rls_school_id() is safe to call when nothing was set."""
        reset_rls_school_id()
        reset_rls_school_id()
