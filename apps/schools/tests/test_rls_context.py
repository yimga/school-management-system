"""
Contract tests for apps.schools.rls_context (§2.4 RUNMYCAMPUS; NEXT_50 step 45 optional).

Ensures set_rls_school_id / reset_rls_school_id are callable and safe for middleware use:
- No-op on non-PostgreSQL; no raise.
- On PostgreSQL, set then reset does not raise (middleware request/response cycle).
"""

import unittest
from unittest.mock import patch

from django.db import connection

from apps.schools.rls_context import (
    reset_rls_bypass,
    reset_rls_school_id,
    rls_bypass,
    rls_school,
    set_rls_bypass,
    set_rls_school_id,
)


class RlsContextContractTests(unittest.TestCase):
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

    def test_set_rls_bypass_callable_no_raise(self):
        """set_rls_bypass() does not raise (no-op on non-postgres)."""
        set_rls_bypass()

    def test_reset_rls_bypass_callable_no_raise(self):
        """reset_rls_bypass() does not raise (no-op on non-postgres)."""
        reset_rls_bypass()

    def test_set_rls_school_id_rejects_none_literal_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id(None)

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_blank_literal_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id("   ")

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_oversized_id_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id("x" * 129)

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_internal_whitespace_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id("school 1")

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_control_character_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id("1\x00")

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_bool_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id(True)
            with self.assertRaises(ValueError):
                set_rls_school_id(False)

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_dict_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id({"id": "1"})

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_binary_buffers_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            for bad in (b"school-1", bytearray(b"school-1"), memoryview(b"school-1")):
                with self.assertRaises(ValueError):
                    set_rls_school_id(bad)

        cursor.assert_not_called()

    def test_set_rls_school_id_rejects_non_string_iterables_on_postgresql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            for bad in (["school-1"], ("school-1",), {"school-1"}):
                with self.assertRaises(ValueError):
                    set_rls_school_id(bad)

        cursor.assert_not_called()

    def test_set_rls_school_id_accepts_string_on_postgresql(self):
        fake_cursor = unittest.mock.MagicMock()
        fake_cm = unittest.mock.MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            set_rls_school_id("school-1")

        fake_cursor.execute.assert_called_once_with(
            "SET app.current_school_id = %s",
            ["school-1"],
        )

    def test_reset_rls_school_id_executes_reset_on_postgresql(self):
        fake_cursor = unittest.mock.MagicMock()
        fake_cm = unittest.mock.MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            reset_rls_school_id()

        fake_cursor.execute.assert_called_once_with("RESET app.current_school_id")

    def test_set_rls_bypass_executes_set_on_postgresql(self):
        fake_cursor = unittest.mock.MagicMock()
        fake_cm = unittest.mock.MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            set_rls_bypass()

        fake_cursor.execute.assert_called_once_with("SET app.rls_bypass = 'on'")

    def test_reset_rls_bypass_executes_reset_on_postgresql(self):
        fake_cursor = unittest.mock.MagicMock()
        fake_cm = unittest.mock.MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            reset_rls_bypass()

        fake_cursor.execute.assert_called_once_with("RESET app.rls_bypass")

    def test_rls_school_context_manager_sets_then_resets(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch("apps.schools.rls_context.set_rls_school_id") as set_school,
            patch("apps.schools.rls_context.reset_rls_school_id") as reset_school,
        ):
            with rls_school("school-1"):
                pass

        set_school.assert_called_once_with("school-1")
        reset_school.assert_called_once_with()

    def test_rls_bypass_context_manager_sets_then_resets(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch("apps.schools.rls_context.set_rls_bypass") as set_bypass,
            patch("apps.schools.rls_context.reset_rls_bypass") as reset_bypass,
        ):
            with rls_bypass():
                pass

        set_bypass.assert_called_once_with()
        reset_bypass.assert_called_once_with()

    def test_set_rls_school_id_rejects_failed_stringification_on_postgresql(self):
        class _BadStringify:
            def __str__(self):
                raise RuntimeError("boom")

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            with self.assertRaises(ValueError):
                set_rls_school_id(_BadStringify())

        cursor.assert_not_called()

    def test_rls_helpers_no_op_when_schema_per_tenant_enabled(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch("apps.schools.rls_context.settings") as mocked_settings,
            patch.object(connection, "cursor") as cursor,
        ):
            mocked_settings.USE_DJANGO_TENANTS = True

            set_rls_school_id("school-1")
            reset_rls_school_id()
            set_rls_bypass()
            reset_rls_bypass()

        cursor.assert_not_called()

    def test_rls_context_managers_no_op_when_schema_per_tenant_enabled(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch("apps.schools.rls_context.settings") as mocked_settings,
            patch.object(connection, "cursor") as cursor,
        ):
            mocked_settings.USE_DJANGO_TENANTS = True

            with rls_school("school-1"):
                pass
            with rls_bypass():
                pass

        cursor.assert_not_called()
