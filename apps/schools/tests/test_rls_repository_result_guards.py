import unittest
from unittest.mock import MagicMock, patch

from django.db import connection


class TestRlsRepositoryResultGuards(unittest.TestCase):
    def test_get_tenant_rls_status_returns_bool_map_for_valid_rows(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = [
            ("people_studentprofile", 1),
            ("schools_school", 0),
        ]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(
                get_tenant_rls_status(["people_studentprofile", "schools_school"]),
                {
                    "people_studentprofile": True,
                    "schools_school": False,
                },
            )

        fake_cursor.execute.assert_called_once()

    def test_get_tenant_rls_status_fetchall_failure_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.side_effect = RuntimeError("boom")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["people_studentprofile"]), {})

        fake_cursor.execute.assert_called_once()

    def test_get_tenant_rls_status_short_result_row_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = [("people_studentprofile",)]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["people_studentprofile"]), {})

        fake_cursor.execute.assert_called_once()
