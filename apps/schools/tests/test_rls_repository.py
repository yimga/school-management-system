"""
Tests for schools.repositories.rls_repository (§2.4 raw SQL in repository).
Non-PG: returns {}. PG: used by verify_tenant_rls command.
"""

import types
import unittest
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection


class TestRlsRepository(unittest.TestCase):
    """RLS repository returns empty dict on non-PG."""

    def test_get_tenant_rls_status_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["people_studentprofile"]), {})

    def test_get_tenant_rls_status_empty_list_returns_empty(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status([]), {})

    def test_get_tenant_rls_status_string_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status("people_studentprofile"), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_bytes_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(b"people_studentprofile"), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_bytearray_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(
                get_tenant_rls_status(bytearray(b"people_studentprofile")),
                {},
            )

        cursor.assert_not_called()

    def test_get_tenant_rls_status_memoryview_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(
                get_tenant_rls_status(memoryview(b"people_studentprofile")),
                {},
            )

        cursor.assert_not_called()

    def test_get_tenant_rls_status_bool_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(True), {})
            self.assertEqual(get_tenant_rls_status(False), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_non_iterable_int_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(1), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_dict_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(
                get_tenant_rls_status({"people_studentprofile": True}),
                {},
            )

        cursor.assert_not_called()

    def test_get_tenant_rls_status_mapping_proxy_input_returns_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            proxy = types.MappingProxyType({"people_studentprofile": True})
            self.assertEqual(get_tenant_rls_status(proxy), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_blank_list_entries_return_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["   ", "\t"]), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_qualified_names_return_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["public.people_studentprofile"]), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_only_non_identifiers_return_empty_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(
                get_tenant_rls_status(["bad-hyphen", "123oops", "x" * 64]),
                {},
            )

        cursor.assert_not_called()

    def test_get_tenant_rls_status_drops_non_identifiers_before_sql(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            get_tenant_rls_status(["people_studentprofile", "bad-hyphen"])

        fake_cursor.execute.assert_called_once()
        params = fake_cursor.execute.call_args[0][1]
        self.assertEqual(params, ["people_studentprofile"])

    def test_get_tenant_rls_status_dedupes_duplicate_identifiers_before_sql(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            get_tenant_rls_status(
                [
                    "people_studentprofile",
                    "people_studentprofile",
                    "schools_school",
                    "schools_school",
                ]
            )

        fake_cursor.execute.assert_called_once()
        params = fake_cursor.execute.call_args[0][1]
        self.assertEqual(params, ["people_studentprofile", "schools_school"])

    def test_get_tenant_rls_status_truncates_excess_identifiers_before_sql(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories import rls_repository
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            cap = rls_repository._RLS_STATUS_MAX_TABLE_NAMES
            names = [f"t{i}" for i in range(cap + 1)]
            get_tenant_rls_status(names)

        fake_cursor.execute.assert_called_once()
        params = fake_cursor.execute.call_args[0][1]
        self.assertEqual(len(params), cap)
        self.assertEqual(params[0], "t0")
        self.assertEqual(params[-1], f"t{cap - 1}")

    def test_get_tenant_rls_status_stops_iterating_once_cap_is_reached(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories import rls_repository
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            cap = rls_repository._RLS_STATUS_MAX_TABLE_NAMES

            def exploding_names():
                for i in range(cap):
                    yield f"t{i}"
                raise AssertionError("iterator advanced past the documented cap")

            get_tenant_rls_status(exploding_names())

        fake_cursor.execute.assert_called_once()
        params = fake_cursor.execute.call_args[0][1]
        self.assertEqual(len(params), cap)
        self.assertEqual(params[-1], f"t{cap - 1}")

    def test_get_tenant_rls_status_does_not_probe_truthiness_before_iteration(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        class _LenGuardIterable:
            def __iter__(self):
                yield "people_studentprofile"

            def __len__(self):
                raise AssertionError("truthiness probe should not run")

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            get_tenant_rls_status(_LenGuardIterable())

        fake_cursor.execute.assert_called_once()
        params = fake_cursor.execute.call_args[0][1]
        self.assertEqual(params, ["people_studentprofile"])

    def test_get_tenant_rls_status_iterator_construction_failure_returns_empty(self):
        class _BadIter:
            def __iter__(self):
                raise RuntimeError("boom")

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(_BadIter()), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_iteration_failure_returns_empty(self):
        def _bad_iter():
            yield "people_studentprofile"
            raise RuntimeError("boom")

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(_bad_iter()), {})

        cursor.assert_not_called()

    def test_get_tenant_rls_status_result_bool_failure_returns_empty(self):
        class _BadBool:
            def __bool__(self):
                raise RuntimeError("boom")

        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = [("people_studentprofile", _BadBool())]
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

    def test_get_tenant_rls_status_skips_when_schema_per_tenant_enabled(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(settings, "USE_DJANGO_TENANTS", True, create=True),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status

            self.assertEqual(get_tenant_rls_status(["people_studentprofile"]), {})

        cursor.assert_not_called()
