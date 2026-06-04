"""Resilient School purge when optional app tables are missing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db.models.deletion import ProtectedError
from django.db.utils import ProgrammingError
from django.test import TestCase

from apps.compliance.tenant_offboarding_inventory import (
    delete_school_record_resilient,
    iter_school_m2m_through_targets,
    purge_public_school_dependencies,
)
from apps.registries.models import EducationSystemTypeRegistry
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


class SchoolM2MThroughPurgeTests(TestCase):
    """Regression: M2M through-table rows (e.g. schools_school_education_system_types)
    must be cleared by the purge. Production failure 2026-06-02 — the collector-bypassing
    ``_raw_delete`` fallback left those join rows, so the raw DELETE on schools_school
    tripped the through table's school_id FK constraint:

        update or delete on table "schools_school" violates foreign key constraint
        "schools_school_educa_school_id_..._fk_schools_s"
        on table "schools_school_education_system_types".
    """

    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="M2M Purge",
            slug="m2m-purge",
            subdomain="m2m-purge",
            is_active=False,
            default_region=self.region,
        )
        self.est = EducationSystemTypeRegistry.objects.create(
            code="m2m-purge-est",
            name="M2M Purge System Type",
        )
        self.school.education_system_types.add(self.est)

    def test_m2m_through_target_is_discovered(self):
        """The auto-created through model carrying School's FK must be enumerated —
        get_models() hides it without include_auto_created, which was the root cause."""
        tables = {m._meta.db_table for m, _f in iter_school_m2m_through_targets()}
        self.assertIn("schools_school_education_system_types", tables)

    def test_purge_clears_m2m_through_rows(self):
        """After purge the join row is gone, so the subsequent School delete won't
        violate the through table's FK."""
        self.assertEqual(self.school.education_system_types.count(), 1)
        purge_public_school_dependencies(self.school)
        self.assertEqual(self.school.education_system_types.count(), 0)
        # And the School row itself can now be removed without an FK violation.
        delete_school_record_resilient(self.school)
        self.assertFalse(School.objects.filter(pk=self.school.pk).exists())


class FixedPointProtectPurgeTests(TestCase):
    """Regression: on_delete=PROTECT FKs between tenant-scoped models mean deletion
    order matters. The purge must defer a PROTECT-blocked parent and retry it after
    its child is cleared, instead of silently abandoning it (which left the later
    School delete to fail with an opaque IntegrityError). Prod offboarding failure
    2026-06-02."""

    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Protect Purge",
            slug="protect-purge",
            subdomain="protect-purge",
            is_active=False,
            default_region=self.region,
        )

    @patch(
        "apps.compliance.tenant_offboarding_inventory.model_table_exists",
        return_value=True,
    )
    @patch(
        "apps.compliance.tenant_offboarding_inventory.iter_school_m2m_through_targets",
        return_value=[],
    )
    @patch("apps.compliance.tenant_offboarding_inventory.iter_school_foreign_key_targets")
    def test_protect_blocked_parent_retried_after_child_cleared(
        self, mock_iter, _m2m, _exists
    ):
        # Parent raises ProtectedError on the first pass, then succeeds once the
        # child has been deleted on that same pass.
        parent = MagicMock()
        parent._meta.label_lower = "academics.department"
        parent._meta.db_table = "academics_department"
        parent_delete = parent._default_manager.filter.return_value.delete
        parent_delete.side_effect = [
            ProtectedError("blocked by specialty", set()),
            (1, {"academics.department": 1}),
        ]

        child = MagicMock()
        child._meta.label_lower = "academics.specialty"
        child._meta.db_table = "academics_specialty"
        child._default_manager.filter.return_value.delete.return_value = (
            1,
            {"academics.specialty": 1},
        )

        mock_iter.return_value = [(parent, "school"), (child, "school")]
        deleted = purge_public_school_dependencies(self.school)

        self.assertEqual(parent_delete.call_count, 2)  # deferred then retried
        self.assertEqual(deleted.get("academics.department"), 1)
        self.assertEqual(deleted.get("academics.specialty"), 1)

    @patch(
        "apps.compliance.tenant_offboarding_inventory.model_table_exists",
        return_value=True,
    )
    @patch(
        "apps.compliance.tenant_offboarding_inventory.iter_school_m2m_through_targets",
        return_value=[],
    )
    @patch("apps.compliance.tenant_offboarding_inventory.iter_school_foreign_key_targets")
    def test_permanent_protect_block_does_not_loop_forever(
        self, mock_iter, _m2m, _exists
    ):
        parent = MagicMock()
        parent._meta.label_lower = "academics.department"
        parent._meta.db_table = "academics_department"
        parent_delete = parent._default_manager.filter.return_value.delete
        parent_delete.side_effect = ProtectedError("always blocked", set())

        mock_iter.return_value = [(parent, "school")]
        # Must return (logging the blocker), not spin forever.
        purge_public_school_dependencies(self.school)
        self.assertEqual(parent_delete.call_count, 1)
