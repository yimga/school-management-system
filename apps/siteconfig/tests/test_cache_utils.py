from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import override_settings
from django.test import SimpleTestCase

from apps.siteconfig.cache_utils import (
    _current_rls_school_id,
    get_tenant_cached,
    get_tenant_cache_prefix,
    set_tenant_cached,
    tenant_cache_key,
)


class TenantCachePrefixTests(SimpleTestCase):
    @override_settings(USE_DJANGO_TENANTS=True)
    def test_current_rls_school_id_skips_in_schema_per_tenant_mode(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            self.assertIsNone(_current_rls_school_id())

        conn.cursor.assert_not_called()

    def test_current_rls_school_id_skips_without_sql_on_non_postgres(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.vendor = "sqlite"

            self.assertIsNone(_current_rls_school_id())

        conn.cursor.assert_not_called()

    def test_current_rls_school_id_returns_normalized_session_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (" school-123 ",)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertEqual(_current_rls_school_id(), "school-123")

        fake_cursor.execute.assert_called_once_with(
            "SELECT current_setting('app.current_school_id', true)"
        )

    def test_current_rls_school_id_database_error_returns_none(self):
        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.side_effect = DatabaseError("boom")
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

        mock_conn.cursor.assert_called_once_with()

    def test_current_rls_school_id_ignores_none_literal_from_session(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("None",)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_null_literal_from_session(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (" null ",)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_oversized_guc_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("x" * 129,)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_whitespace_inside_guc_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("12 34",)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_bool_guc_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (True,)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_binary_buffer_guc_value(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (memoryview(b"1"),)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_current_rls_school_id_ignores_mapping_proxy_guc_value(self):
        """Empty read-only mapping stringifies to '{}', which otherwise passes length/whitespace checks."""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (MappingProxyType({}),)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.return_value = fake_context
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

    def test_get_tenant_cache_prefix_uses_request_school_id_when_present(self):
        request = SimpleNamespace(school=SimpleNamespace(id="school-123"))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "school:school-123")

    def test_get_tenant_cache_prefix_ignores_none_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id=None))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_blank_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id="   "))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_null_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id=" null "))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_oversized_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id="x" * 129))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_internal_space_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id="school 1"))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_bool_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id=True))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_binary_buffer_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id=b"school-1"))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_mapping_request_school_id(self):
        request = SimpleNamespace(school=SimpleNamespace(id=MappingProxyType({})))

        with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
            self.assertEqual(get_tenant_cache_prefix(request), "public")

    def test_get_tenant_cache_prefix_ignores_dict_tenant_schema_name(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.tenant = SimpleNamespace(schema_name={"schema": "tenant_a"})
            with patch(
                "apps.siteconfig.cache_utils._current_rls_school_id", return_value=None
            ):
                self.assertEqual(get_tenant_cache_prefix(), "public")

    def test_get_tenant_cache_prefix_ignores_bool_tenant_schema_name(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.tenant = SimpleNamespace(schema_name=True)
            with patch(
                "apps.siteconfig.cache_utils._current_rls_school_id", return_value=None
            ):
                self.assertEqual(get_tenant_cache_prefix(), "public")

    def test_get_tenant_cache_prefix_uses_normalized_tenant_schema(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.tenant = SimpleNamespace(schema_name="tenant_acme")
            self.assertEqual(get_tenant_cache_prefix(), "tenant:tenant_acme")

    def test_get_tenant_cache_prefix_ignores_malformed_tenant_schema_name(self):
        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.tenant = SimpleNamespace(schema_name="tenant-bad")
            with patch(
                "apps.siteconfig.cache_utils._current_rls_school_id", return_value=None
            ):
                self.assertEqual(get_tenant_cache_prefix(), "public")

    def test_get_tenant_cached_skips_blank_lookup_without_cache_get(self):
        with patch("apps.siteconfig.cache_utils.cache") as mock_cache:
            self.assertIsNone(get_tenant_cached("   "))
        mock_cache.get.assert_not_called()

    def test_get_tenant_cached_skips_overlong_lookup_without_cache_get(self):
        with patch("apps.siteconfig.cache_utils.cache") as mock_cache:
            self.assertIsNone(get_tenant_cached("x" * 513))
        mock_cache.get.assert_not_called()

    def test_set_tenant_cached_skips_invalid_lookup_without_cache_set(self):
        with patch("apps.siteconfig.cache_utils.cache") as mock_cache:
            set_tenant_cached("bad\nkey", {"ok": True})
        mock_cache.set.assert_not_called()

    def test_tenant_cache_key_strips_base_segment(self):
        with patch(
            "apps.siteconfig.cache_utils.get_tenant_cache_prefix",
            return_value="school:1",
        ):
            self.assertEqual(tenant_cache_key("  widget  "), "school:1:widget")

    def test_tenant_cache_key_replaces_malformed_base_with_fallback(self):
        with patch(
            "apps.siteconfig.cache_utils.get_tenant_cache_prefix",
            return_value="public",
        ):
            self.assertEqual(tenant_cache_key(""), "public:_")
            self.assertEqual(tenant_cache_key("bad\nx"), "public:_")
            self.assertEqual(tenant_cache_key("x" * 513), "public:_")

    def test_tenant_cache_key_non_string_base_uses_fallback(self):
        with patch(
            "apps.siteconfig.cache_utils.get_tenant_cache_prefix",
            return_value="public",
        ):
            self.assertEqual(tenant_cache_key(None), "public:_")  # type: ignore[arg-type]
