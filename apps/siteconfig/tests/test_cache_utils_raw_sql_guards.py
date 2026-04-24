from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.siteconfig.cache_utils import (
    _current_rls_school_id,
    get_tenant_cached,
    get_tenant_cache_prefix,
    set_tenant_cached,
)


class _BrokenTenantConnection:
    vendor = "postgresql"

    @property
    def tenant(self):
        raise RuntimeError("tenant unavailable")


class TenantCacheRawSqlGuardTests(SimpleTestCase):
    def test_current_rls_school_id_runtime_error_returns_none(self):
        mock_conn = MagicMock()
        mock_conn.vendor = "postgresql"
        mock_conn.cursor.side_effect = RuntimeError("boom")
        with (
            patch("apps.siteconfig.cache_utils.connection", mock_conn),
            patch(
                "apps.siteconfig.repositories.rls_session_repository.connection",
                mock_conn,
            ),
        ):
            self.assertIsNone(_current_rls_school_id())

        mock_conn.cursor.assert_called_once_with()

    def test_current_rls_school_id_missing_row_returns_none(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = None
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

        fake_cursor.execute.assert_called_once_with(
            "SELECT current_setting('app.current_school_id', true)"
        )

    def test_get_tenant_cache_prefix_prefers_tenant_schema_over_rls_and_request(self):
        request = SimpleNamespace(school=SimpleNamespace(id="school-request"))

        with patch("apps.siteconfig.cache_utils.connection") as conn:
            conn.tenant = SimpleNamespace(schema_name="tenant_acme")
            with patch(
                "apps.siteconfig.cache_utils._current_rls_school_id",
                return_value="school-rls",
            ):
                self.assertEqual(
                    get_tenant_cache_prefix(request),
                    "tenant:tenant_acme",
                )

    def test_get_tenant_cache_prefix_recovers_when_tenant_lookup_raises(self):
        request = SimpleNamespace(school=SimpleNamespace(id="school-request"))

        with patch(
            "apps.siteconfig.cache_utils.connection",
            new=_BrokenTenantConnection(),
        ):
            with patch("apps.siteconfig.cache_utils._current_rls_school_id", return_value=None):
                self.assertEqual(
                    get_tenant_cache_prefix(request),
                    "school:school-request",
                )

    def test_get_tenant_cached_cache_runtime_error_returns_none(self):
        with patch("apps.siteconfig.cache_utils.cache") as mock_cache:
            mock_cache.get.side_effect = RuntimeError("cache unavailable")

            self.assertIsNone(get_tenant_cached("tenant.example.edu"))

        mock_cache.get.assert_called_once_with(
            "tenant_resolution:tenant.example.edu"
        )

    def test_set_tenant_cached_cache_value_error_is_swallowed(self):
        payload = {"school_id": "school-1"}

        with patch("apps.siteconfig.cache_utils.cache") as mock_cache:
            mock_cache.set.side_effect = ValueError("cache unavailable")

            set_tenant_cached("tenant.example.edu", payload)

        mock_cache.set.assert_called_once_with(
            "tenant_resolution:tenant.example.edu",
            payload,
            timeout=300,
        )
