from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase, override_settings

from apps.schools.tenant_url import get_single_tenant_slug


class TenantUrlHelperTests(SimpleTestCase):
    def test_get_single_tenant_slug_returns_none_when_legacy_disabled(self):
        self.assertIsNone(get_single_tenant_slug())

    @override_settings(SINGLE_TENANT="true")
    def test_get_single_tenant_slug_returns_none_on_query_failure(self):
        with patch(
            "apps.schools.models.School.objects.filter", side_effect=DatabaseError
        ):
            self.assertIsNone(get_single_tenant_slug())
