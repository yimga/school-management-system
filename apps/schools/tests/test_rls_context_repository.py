from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.schools.repositories.rls_context_repository import (
    reset_current_school_id,
    reset_rls_bypass_var,
    set_current_school_id,
    set_rls_bypass_on,
)


class RlsContextRepositoryTests(SimpleTestCase):
    def test_set_current_school_id_parameterized(self):
        fake_cursor = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_cm
        with patch(
            "apps.schools.repositories.rls_context_repository.connection",
            mock_conn,
        ):
            set_current_school_id("school-1")

        fake_cursor.execute.assert_called_once_with(
            "SET app.current_school_id = %s",
            ["school-1"],
        )

    def test_reset_current_school_id(self):
        fake_cursor = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_cm
        with patch(
            "apps.schools.repositories.rls_context_repository.connection",
            mock_conn,
        ):
            reset_current_school_id()

        fake_cursor.execute.assert_called_once_with("RESET app.current_school_id")

    def test_set_rls_bypass_on(self):
        fake_cursor = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_cm
        with patch(
            "apps.schools.repositories.rls_context_repository.connection",
            mock_conn,
        ):
            set_rls_bypass_on()

        fake_cursor.execute.assert_called_once_with("SET app.rls_bypass = 'on'")

    def test_reset_rls_bypass_var(self):
        fake_cursor = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_cm
        with patch(
            "apps.schools.repositories.rls_context_repository.connection",
            mock_conn,
        ):
            reset_rls_bypass_var()

        fake_cursor.execute.assert_called_once_with("RESET app.rls_bypass")
