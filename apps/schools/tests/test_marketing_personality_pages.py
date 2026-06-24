"""MULTI-PERSONALITY-GRID — dedicated marketing viewport pages."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from django.test import SimpleTestCase
from django.urls import reverse

from apps.schools.marketing_media_matrix import marketing_copy_token
from apps.schools.marketing_personality_registry import (
    get_personality_page,
    personality_slugs,
)
from apps.schools.marketing_url_inventory import (
    ACQUISITION_PERSONALITY_SLUGS,
    iter_marketing_acquisition_smoke_targets,
)

REPO = Path(__file__).resolve().parents[3]


class MarketingPersonalityPagesTests(SimpleTestCase):
    def test_registry_slugs(self):
        slugs = personality_slugs()
        for slug in (
            "zero-ui",
            "enterprise-ledger",
            "academics",
            "edge-mesh",
            "compliance",
            "pricing",
        ):
            self.assertIn(slug, slugs)
            spec = get_personality_page(slug)
            self.assertIsNotNone(spec)
            self.assertTrue((REPO / "templates" / spec["template"]).is_file())

    def test_reverse_personality_urls(self):
        self.assertEqual(
            reverse("marketing_personality_page", kwargs={"personality_slug": "zero-ui"}),
            "/experience/zero-ui/",
        )

    def test_copy_tokens_us_and_sa(self):
        us = marketing_copy_token("US", "txt_academics_headline", {})
        self.assertNotIn("[txt_", us)
        sa = marketing_copy_token("SA", "txt_compliance_headline", {})
        self.assertTrue(sa)

    def test_zero_ui_template_playground(self):
        text = (REPO / "templates/marketing/zero_ui_lab.html").read_text(encoding="utf-8")
        partial = (
            REPO / "templates/marketing/partials/sections/_zero_ui_lab.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-mkt-personality-page="zero-ui"', text)
        self.assertIn("mkt-zero-ui-playground.js", text)
        self.assertIn("data-mkt-zero-ui-playground", partial)

    def test_enterprise_ledger_constellation(self):
        text = (REPO / "templates/marketing/enterprise_ledger.html").read_text(
            encoding="utf-8"
        )
        partial = (
            REPO
            / "templates/marketing/partials/sections/_enterprise_constellation.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-mkt-personality-page="enterprise-ledger"', text)
        self.assertIn("_enterprise_constellation.html", text)
        self.assertIn("data-mkt-enterprise-constellation", partial)

    def test_homepage_one_record_scroll(self):
        text = (REPO / "templates/marketing/homepage.html").read_text(encoding="utf-8")
        stage = (
            REPO / "templates/marketing/partials/one_record_scroll/_stage_speed_duel.html"
        ).read_text(encoding="utf-8")
        self.assertIn("_one_record_scroll.html", text)
        self.assertIn("mkt-one-record-scroll.js", text)
        self.assertIn("mkt-speed-duel.js", text)
        self.assertIn("data-mkt-speed-duel", stage)

    def test_edge_mesh_trinity(self):
        text = (REPO / "templates/marketing/edge_mesh.html").read_text(encoding="utf-8")
        partial = (
            REPO / "templates/marketing/partials/sections/_viewport_trinity.html"
        ).read_text(encoding="utf-8")
        self.assertIn("_viewport_trinity.html", text)
        self.assertIn("data-mkt-viewport-trinity", partial)

    def test_acquisition_smoke_inventory(self):
        targets = iter_marketing_acquisition_smoke_targets()
        paths = {t.path for t in targets}
        self.assertIn("/storefront/", paths)
        for slug in ACQUISITION_PERSONALITY_SLUGS:
            self.assertIn(f"/experience/{slug}/", paths)

    def test_academics_template_viewport(self):
        text = (REPO / "templates/marketing/academics.html").read_text(encoding="utf-8")
        self.assertIn('data-mkt-personality-page="academics"', text)
        self.assertIn("mkt-gradebook-morph.js", text)

    def test_edge_mesh_drop_simulator(self):
        rugged = (
            REPO / "templates/marketing/partials/sections/_rugged_engine.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-mkt-drop-simulator", rugged)
        self.assertIn('data-mkt-network="blackout"', rugged)

    def test_personality_pages_verifier(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_personality_pages.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_internal_audit_orchestrator(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_lane2_internal_audit.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("MARKETING_LANE2_INTERNAL_AUDIT_PASS", proc.stdout)
