"""0075 backfill: region-less schools linked to existing RegionConfig rows."""

from __future__ import annotations

import importlib
import uuid

from django.apps import apps as django_apps
from django.db import connection
from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import RegionConfig

_MIGRATION = importlib.import_module(
    "apps.schools.migrations.0075_backfill_school_default_region"
)


class BackfillDefaultRegionMigrationTests(TestCase):
    @staticmethod
    def _school(**kw):
        tag = uuid.uuid4().hex[:10]
        defaults = {
            "name": f"Backfill {tag}",
            "slug": f"backfill-{tag}",
            "subdomain": f"backfill-{tag}",
            "is_active": False,
        }
        defaults.update(kw)
        return School.objects.create(**defaults)

    @staticmethod
    def _region(code: str, name: str) -> RegionConfig:
        region, _ = RegionConfig.objects.get_or_create(
            code=code, defaults={"name": name}
        )
        return region

    def _run_backfill(self):
        # Migration only reads ``schema_editor.connection.alias``; avoid entering
        # SQLite's schema editor inside TestCase's atomic block (NotSupportedError).
        class _SchemaEditorStub:
            connection = connection

        _MIGRATION.backfill_default_region(django_apps, _SchemaEditorStub())

    def test_backfill_links_region_less_school_with_matching_country(self):
        self._region("USA", "United States")
        school = self._school(country_code="", default_region=None)
        # Simulate admin/import rows that bypass School.save auto-link.
        School.objects.filter(pk=school.pk).update(
            country_code="US", default_region_id=None
        )
        school.refresh_from_db()
        self.assertIsNone(school.default_region_id)

        self._run_backfill()

        school.refresh_from_db()
        self.assertEqual(school.default_region_id, "USA")

    def test_backfill_does_not_override_explicit_region(self):
        usa = self._region("USA", "United States")
        cmr = self._region("CMR", "Cameroon")
        school = self._school(country_code="US", default_region=cmr)

        self._run_backfill()

        school.refresh_from_db()
        self.assertEqual(school.default_region_id, cmr.code)
        self.assertNotEqual(school.default_region_id, usa.code)

    def test_backfill_skips_school_when_no_region_row(self):
        school = self._school(country_code="", default_region=None)
        School.objects.filter(pk=school.pk).update(
            country_code="ZZ", default_region_id=None
        )
        school.refresh_from_db()

        self._run_backfill()

        school.refresh_from_db()
        self.assertIsNone(school.default_region_id)
