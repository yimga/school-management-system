"""Scroll compression wave 2 — catalog pagination contract (batch 1574)."""

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

REPO = Path(__file__).resolve().parents[3]
METADATA_CATALOG = REPO / "templates/schools/super_metadata_catalog.html"


class ScrollCompressionCatalogPaginationTests(SimpleTestCase):
    def test_verifier_script_passes(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "scripts/verify_scroll_compression_catalog_pagination.py"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=proc.stderr or proc.stdout,
        )
        self.assertIn("SCROLL_COMPRESSION_CATALOG_PAGINATION_PASS", proc.stdout)

    def test_policies_view_dropped_hard_cap_slice(self):
        src = (REPO / "apps/schools/super_views_catalog.py").read_text(encoding="utf-8")
        chunk = src.split("def super_policies_catalog", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("[:200]", chunk)

    def test_metadata_catalog_uses_queryset_pagination(self):
        src = (REPO / "apps/schools/super_views_catalog.py").read_text(encoding="utf-8")
        chunk = src.split("def super_metadata_catalog", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("metadata_catalog_queryset", chunk)
        self.assertNotIn("max_entities=200", chunk)

    def test_metadata_services_exposes_queryset_helper(self):
        src = (REPO / "apps/metadata/services.py").read_text(encoding="utf-8")
        self.assertIn("def metadata_catalog_queryset", src)
        self.assertIn("def annotate_metadata_catalog_entities", src)

    def test_migration_conflicts_dropped_hard_caps(self):
        src = (REPO / "apps/migration_cloud/views.py").read_text(encoding="utf-8")
        chunk = src.split("class MigrationCloudConflictsView", 1)[1].split("\nclass ", 1)[0]
        self.assertNotIn("[:200]", chunk)
        self.assertNotIn("[:50]", chunk)
        self.assertIn("resolved_page_obj", chunk)

    def test_field_impact_view_paginates(self):
        src = (REPO / "apps/schools/super_views_catalog.py").read_text(encoding="utf-8")
        chunk = src.split("def super_metadata_catalog_field_impact", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_paginate_queryset", chunk)
        self.assertIn("dependencies_total", chunk)

    def test_app_catalog_view_paginates(self):
        src = (REPO / "apps/marketplace/views.py").read_text(encoding="utf-8")
        chunk = src.split("def app_catalog", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("Paginator", chunk)
        self.assertIn("page_obj", chunk)

    def test_bundle_detail_artifacts_paginate(self):
        src = (REPO / "apps/migration_cloud/views.py").read_text(encoding="utf-8")
        chunk = src.split("class MigrationCloudBundleDetailView", 1)[1].split("\nclass ", 1)[0]
        self.assertIn("artifacts_page_obj", chunk)
        self.assertNotIn("bundle.artifacts.all(),", chunk)

    def test_metadata_catalog_field_overflow_annotation(self):
        src = (REPO / "apps/metadata/services.py").read_text(encoding="utf-8")
        self.assertIn("METADATA_CATALOG_FIELD_PREVIEW", src)
        self.assertIn("fields_overflow", src)
        meta_tpl = (REPO / "templates/schools/super_metadata_catalog.html").read_text(
            encoding="utf-8"
        )
        # field_preview is the CONTEXT VARIABLE the template loops over and the
        # slice check is an ABSENCE -- both template code / byte questions, so
        # both stay reads. This is a catalog PAGINATION contract, so what the
        # parser can settle is that the catalog page still is a catalog and still
        # pulls in the pager that replaced the truncating slice.
        assert_markup(self, METADATA_CATALOG, 'data-page-archetype="catalog"')
        assert_wires(self, METADATA_CATALOG, "components/pagination.html")
        self.assertNotIn('|slice:":10"', meta_tpl)
        self.assertIn("field_preview", meta_tpl)
