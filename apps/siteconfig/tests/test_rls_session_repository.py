from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.siteconfig.repositories.rls_session_repository import (
    fetch_current_school_id_setting_value,
)


class RlsSessionRepositoryTests(SimpleTestCase):
    def test_fetch_returns_first_column_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("school-1",)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_context
        with patch(
            "apps.siteconfig.repositories.rls_session_repository.connection",
            mock_conn,
        ):
            self.assertEqual(fetch_current_school_id_setting_value(), "school-1")

        fake_cursor.execute.assert_called_once_with(
            "SELECT current_setting('app.current_school_id', true)"
        )

    def test_fetch_returns_none_when_no_row(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = None
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = fake_context
        with patch(
            "apps.siteconfig.repositories.rls_session_repository.connection",
            mock_conn,
        ):
            self.assertIsNone(fetch_current_school_id_setting_value())

    def test_fetch_cursor_runtime_error_returns_none(self):
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = RuntimeError("boom")
        with patch(
            "apps.siteconfig.repositories.rls_session_repository.connection",
            mock_conn,
        ):
            self.assertIsNone(fetch_current_school_id_setting_value())

        mock_conn.cursor.assert_called_once_with()
