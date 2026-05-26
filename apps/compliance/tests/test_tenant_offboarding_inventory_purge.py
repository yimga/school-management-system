"""Resilient School purge when optional app tables are missing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db.utils import ProgrammingError
from django.test import TestCase

from apps.compliance.tenant_offboarding_inventory import (
    delete_school_record_resilient,
    purge_public_school_dependencies,
)
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class ResilientSchoolDeleteTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Missing Table Purge",
            slug="missing-table-purge",
            subdomain="missing-table-purge",
            is_active=False,
            default_region=self.region,
        )

    @patch(
        "apps.compliance.tenant_offboarding_inventory.model_table_exists",
        return_value=False,
    )
    def test_purge_dependencies_skips_missing_tables(self, _exists):
        deleted = purge_public_school_dependencies(self.school)
        self.assertEqual(deleted, {})
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    @patch(
        "apps.compliance.tenant_offboarding_inventory.purge_public_school_dependencies",
        return_value={},
    )
    def test_delete_uses_raw_delete_when_collector_fails(self, _purge):
        school = School.objects.create(
            name="Collector Fail",
            slug="collector-fail-purge",
            subdomain="collector-fail-purge",
            is_active=False,
            default_region=self.region,
        )
        mock_qs = MagicMock()
        mock_qs.delete.side_effect = ProgrammingError(
            'relation "portal_hostedofficedocument" does not exist'
        )
        mock_qs.db = "default"
        with patch.object(School._default_manager, "filter", return_value=mock_qs):
            delete_school_record_resilient(school)
        mock_qs._raw_delete.assert_called_once_with(using="default")
