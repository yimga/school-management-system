"""Tenant column-mapping review — surface the auto-map + let a tenant correct it.

The tenant upload flow auto-maps each source column to a canonical field and
persists it to ``MigrationBundle.mapping_summary['per_artifact']``, but the
tenant review page only ever exposed the per-FILE record type — the column
mapping was silent, with no way to fix a wrong one before import. These lock the
new review surface:

* ``_column_mapping_rows`` shapes the persisted mapping for the UI and flags the
  quarantine-safe ``custom_fields.*`` columns as "kept as custom" (nothing lost);
* ``_field_choices_for_domain`` offers the ontology's real fields for the file's
  domain (and an honest empty list for a domain with no ontology);
* ``_apply_column_overrides`` rewrites the SAME ``mapping_summary`` the apply
  reads (matched by source column, method ``tenant_override``) so a tenant's
  correction reaches landed data exactly as an operator's does — and is a no-op
  when nothing actually changed.
"""
from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.views_tenant_upload import (
    TenantMigrationReviewView,
    _column_mapping_rows,
    _field_choices_for_domain,
)


class ColumnMappingHelperTests(SimpleTestCase):
    def test_rows_shape_and_custom_flag(self):
        rows = _column_mapping_rows(
            [
                {"source_column": "Given Name", "canonical_field": "first_name", "confidence": 0.98, "method": "alias"},
                {"source_column": "Mystery", "canonical_field": "custom_fields.mystery", "confidence": 0.0, "method": "custom_field"},
                "not-a-dict",  # must be ignored, not crash
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["canonical_field"], "first_name")
        self.assertFalse(rows[0]["is_custom"])
        self.assertEqual(rows[0]["confidence_pct"], 98)
        self.assertTrue(rows[1]["is_custom"])  # custom_fields.* → kept as custom

    def test_field_choices_known_vs_unknown_domain(self):
        students = _field_choices_for_domain("students")
        self.assertIn("first_name", students)
        # A header-only domain with no ontology yields an honest empty list,
        # not a misleading set of foreign fields.
        self.assertEqual(_field_choices_for_domain("no_such_domain"), [])
        self.assertEqual(_field_choices_for_domain(""), [])


class ColumnMappingOverrideTests(TestCase):
    def setUp(self):
        self.bundle = MigrationBundle.objects.create(
            label="colmap test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"tenant-colmap-{self.id()}",
            status=BundleStatus.MAPPED,
            mapping_summary={
                "per_artifact": {
                    "students.csv": [
                        {"source_column": "Given Name", "canonical_field": "first_name", "confidence": 0.98, "method": "alias"},
                        {"source_column": "Mystery", "canonical_field": "custom_fields.mystery", "confidence": 0.0, "method": "custom_field"},
                    ]
                }
            },
            schema_name="public",
        )
        self.art = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="students.csv",
            filename="students.csv",
            byte_size=12,
            sha256="c" * 64,
            assigned_domain="students",
        )

    def test_override_rewrites_mapping_in_place(self):
        req = RequestFactory().post(
            "/x/",
            {
                f"map__{self.art.pk}__1": "last_name",  # correct the mystery column
                f"mapsrc__{self.art.pk}__1": "Mystery",
            },
        )
        changed = TenantMigrationReviewView()._apply_column_overrides(req, self.bundle)
        self.assertEqual(changed, 1)
        self.bundle.refresh_from_db()
        maps = self.bundle.mapping_summary["per_artifact"]["students.csv"]
        target = next(m for m in maps if m["source_column"] == "Mystery")
        self.assertEqual(target["canonical_field"], "last_name")
        self.assertEqual(target["method"], "tenant_override")
        self.assertGreaterEqual(target["confidence"], 0.95)
        # The untouched column is left exactly as it was.
        first = next(m for m in maps if m["source_column"] == "Given Name")
        self.assertEqual(first["canonical_field"], "first_name")
        self.assertEqual(first["method"], "alias")

    def test_override_is_noop_when_value_unchanged(self):
        req = RequestFactory().post(
            "/x/",
            {
                f"map__{self.art.pk}__0": "first_name",  # same as stored
                f"mapsrc__{self.art.pk}__0": "Given Name",
            },
        )
        changed = TenantMigrationReviewView()._apply_column_overrides(req, self.bundle)
        self.assertEqual(changed, 0)

    def test_override_matches_by_source_column_not_index(self):
        # Even if the POST index does not line up with list order, the override
        # is applied to the mapping whose SOURCE COLUMN matches (robust to any
        # reordering between render and submit).
        req = RequestFactory().post(
            "/x/",
            {
                f"map__{self.art.pk}__0": "middle_name",
                f"mapsrc__{self.art.pk}__0": "Mystery",  # index 0 key, but names the 2nd column
            },
        )
        changed = TenantMigrationReviewView()._apply_column_overrides(req, self.bundle)
        self.assertEqual(changed, 1)
        self.bundle.refresh_from_db()
        maps = self.bundle.mapping_summary["per_artifact"]["students.csv"]
        self.assertEqual(
            next(m for m in maps if m["source_column"] == "Mystery")["canonical_field"],
            "middle_name",
        )
