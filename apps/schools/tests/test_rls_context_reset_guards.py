import unittest
from unittest.mock import patch

from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from apps.schools.rls_context import rls_bypass, rls_school


class RlsContextResetGuardTests(unittest.TestCase):
    def test_rls_school_reset_operational_error_is_swallowed_and_logged(self):
        with (
            patch(
                "apps.schools.rls_context._should_manage_rls_session_vars",
                return_value=True,
            ),
            patch("apps.schools.rls_context.set_rls_school_id") as set_school,
            patch(
                "apps.schools.rls_context.reset_rls_school_id",
                side_effect=OperationalError("boom"),
            ) as reset_school,
            self.assertLogs("apps.schools.rls_context", level="DEBUG") as captured,
        ):
            with rls_school("school-1"):
                pass

        set_school.assert_called_once_with("school-1")
        reset_school.assert_called_once_with()
        self.assertTrue(
            any("RLS reset app.current_school_id: boom" in message for message in captured.output)
        )

    def test_rls_school_reset_programming_error_is_swallowed_and_logged(self):
        with (
            patch(
                "apps.schools.rls_context._should_manage_rls_session_vars",
                return_value=True,
            ),
            patch("apps.schools.rls_context.set_rls_school_id") as set_school,
            patch(
                "apps.schools.rls_context.reset_rls_school_id",
                side_effect=ProgrammingError("bad reset"),
            ) as reset_school,
            self.assertLogs("apps.schools.rls_context", level="DEBUG") as captured,
        ):
            with rls_school("school-1"):
                pass

        set_school.assert_called_once_with("school-1")
        reset_school.assert_called_once_with()
        self.assertTrue(
            any(
                "RLS reset app.current_school_id: bad reset" in message
                for message in captured.output
            )
        )

    def test_rls_bypass_reset_database_error_is_swallowed(self):
        with (
            patch(
                "apps.schools.rls_context._should_manage_rls_session_vars",
                return_value=True,
            ),
            patch("apps.schools.rls_context.set_rls_bypass") as set_bypass,
            patch(
                "apps.schools.rls_context.reset_rls_bypass",
                side_effect=DatabaseError("boom"),
            ) as reset_bypass,
            self.assertLogs("apps.schools.rls_context", level="DEBUG") as captured,
        ):
            with rls_bypass():
                pass

        set_bypass.assert_called_once_with()
        reset_bypass.assert_called_once_with()
        self.assertTrue(
            any("RLS reset app.rls_bypass: boom" in m for m in captured.output)
        )

    def test_rls_bypass_reset_operational_error_is_swallowed_and_logged(self):
        with (
            patch(
                "apps.schools.rls_context._should_manage_rls_session_vars",
                return_value=True,
            ),
            patch("apps.schools.rls_context.set_rls_bypass") as set_bypass,
            patch(
                "apps.schools.rls_context.reset_rls_bypass",
                side_effect=OperationalError("bypass reset"),
            ) as reset_bypass,
            self.assertLogs("apps.schools.rls_context", level="DEBUG") as captured,
        ):
            with rls_bypass():
                pass

        set_bypass.assert_called_once_with()
        reset_bypass.assert_called_once_with()
        self.assertTrue(
            any("RLS reset app.rls_bypass: bypass reset" in m for m in captured.output)
        )

    def test_rls_bypass_reset_programming_error_is_swallowed_and_logged(self):
        with (
            patch(
                "apps.schools.rls_context._should_manage_rls_session_vars",
                return_value=True,
            ),
            patch("apps.schools.rls_context.set_rls_bypass") as set_bypass,
            patch(
                "apps.schools.rls_context.reset_rls_bypass",
                side_effect=ProgrammingError("bad bypass reset"),
            ) as reset_bypass,
            self.assertLogs("apps.schools.rls_context", level="DEBUG") as captured,
        ):
            with rls_bypass():
                pass

        set_bypass.assert_called_once_with()
        reset_bypass.assert_called_once_with()
        self.assertTrue(
            any(
                "RLS reset app.rls_bypass: bad bypass reset" in m for m in captured.output
            )
        )
