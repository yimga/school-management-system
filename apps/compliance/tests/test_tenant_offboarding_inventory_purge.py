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
        "apps.compliance.tenant_offboarding_inventory._snapshot_public_table_set",
        return_value=set(),
    )
    def test_purge_dependencies_skips_missing_tables(self, _snapshot):
        """Empty snapshot ⇒ every FK model's table is treated as missing ⇒ loop skips
        them all without attempting a delete. Mirrors the v4.00.1 cache-path contract:
        ``_snapshot_public_table_set`` is the SOT for table presence."""
        deleted = purge_public_school_dependencies(self.school)
        self.assertEqual(deleted, {})
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    @patch(
        "apps.compliance.tenant_offboarding_inventory.model_table_exists",
        return_value=True,
    )
    @patch("apps.compliance.tenant_offboarding_inventory.iter_school_foreign_key_targets")
    def test_purge_dependencies_continues_after_per_model_db_error(
        self, mock_iter, _exists
    ):
        model_ok = MagicMock()
        model_ok._meta.label_lower = "siteconfig.sitesettings"
        model_ok._meta.db_table = "siteconfig_sitesettings"
        model_ok._default_manager.filter.return_value.delete.return_value = (1, {})

        model_bad = MagicMock()
        model_bad._meta.label_lower = "portal.hostedofficedocument"
        model_bad._meta.db_table = "portal_hostedofficedocument"
        model_bad._default_manager.filter.return_value.delete.side_effect = (
            ProgrammingError('relation "portal_hostedofficedocument" does not exist')
        )

        mock_iter.return_value = [
            (model_bad, "school"),
            (model_ok, "school"),
        ]
        deleted = purge_public_school_dependencies(self.school)
        self.assertEqual(deleted.get("siteconfig.sitesettings"), 1)
        model_ok._default_manager.filter.assert_called()

    @patch(
        "apps.compliance.tenant_offboarding_inventory.model_table_exists",
        return_value=True,
    )
    @patch("apps.compliance.tenant_offboarding_inventory.iter_school_foreign_key_targets")
    def test_purge_dependencies_recovers_from_psycopg_operational_error(
        self, mock_iter, _exists
    ):
        """Production bug 2026-05-28: psycopg.OperationalError raised by django-tenants'
        ``SET search_path`` is NOT a subclass of django.db.utils.DatabaseError. Earlier
        narrow catch let it escape and 500'd the purge. Verify the broad catch holds."""

        class _FakePsycopgOperationalError(Exception):
            """Stand-in for psycopg.OperationalError so the test does not require psycopg."""

        model_bad = MagicMock()
        model_bad._meta.label_lower = "finance.parentwallet"
        model_bad._meta.db_table = "finance_parentwallet"
        model_bad._default_manager.filter.return_value.delete.side_effect = (
            _FakePsycopgOperationalError(
                "sending query failed: another command is already in progress"
            )
        )

        model_ok = MagicMock()
        model_ok._meta.label_lower = "siteconfig.sitesettings"
        model_ok._meta.db_table = "siteconfig_sitesettings"
        model_ok._default_manager.filter.return_value.delete.return_value = (1, {})

        mock_iter.return_value = [
            (model_bad, "school"),
            (model_ok, "school"),
        ]
        deleted = purge_public_school_dependencies(self.school)
        self.assertEqual(deleted.get("siteconfig.sitesettings"), 1)
        self.assertNotIn("finance.parentwallet", deleted)

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
