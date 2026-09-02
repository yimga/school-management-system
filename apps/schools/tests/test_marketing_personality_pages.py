"""MULTI-PERSONALITY-GRID — dedicated marketing viewport pages."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
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
from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

REPO = Path(__file__).resolve().parents[3]

ACADEMICS = REPO / "templates/marketing/academics.html"
EDGE_MESH = REPO / "templates/marketing/edge_mesh.html"
ENTERPRISE_LEDGER = REPO / "templates/marketing/enterprise_ledger.html"
HOMEPAGE = REPO / "templates/marketing/homepage.html"
ZERO_UI_LAB = REPO / "templates/marketing/zero_ui_lab.html"
SECTIONS = REPO / "templates/marketing/partials/sections"
CONSTELLATION = SECTIONS / "_enterprise_constellation.html"
RUGGED_ENGINE = SECTIONS / "_rugged_engine.html"
VIEWPORT_TRINITY = SECTIONS / "_viewport_trinity.html"
ZERO_UI_LAB_SECTION = SECTIONS / "_zero_ui_lab.html"
SPEED_DUEL_STAGE = (
    REPO / "templates/marketing/partials/one_record_scroll/_stage_speed_duel.html"
)


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
        # A {% static %} argument is not emitted text, so only the source read can
        # see the bundle name. The markup and the wiring are asked of the engine.
        self.assertIn("mkt-zero-ui-playground.js", text)
        assert_markup(self, ZERO_UI_LAB, 'data-mkt-personality-page="zero-ui"')
        assert_wires(self, ZERO_UI_LAB, "_zero_ui_lab.html")
        assert_markup(self, ZERO_UI_LAB_SECTION, "data-mkt-zero-ui-playground")

    def test_enterprise_ledger_constellation(self):
        assert_markup(
            self, ENTERPRISE_LEDGER, 'data-mkt-personality-page="enterprise-ledger"'
        )
        assert_wires(self, ENTERPRISE_LEDGER, "_enterprise_constellation.html")
        assert_markup(self, CONSTELLATION, "data-mkt-enterprise-constellation")

    def test_homepage_one_record_scroll(self):
        text = (REPO / "templates/marketing/homepage.html").read_text(encoding="utf-8")
        # Both bundles are {% static %} arguments; a parse cannot see either.
        self.assertIn("mkt-one-record-scroll.js", text)
        self.assertIn("mkt-speed-duel.js", text)
        assert_wires(self, HOMEPAGE, "_one_record_scroll.html")
        assert_markup(self, SPEED_DUEL_STAGE, "data-mkt-speed-duel")

    def test_edge_mesh_trinity(self):
        assert_wires(self, EDGE_MESH, "_viewport_trinity.html")
        assert_markup(self, VIEWPORT_TRINITY, "data-mkt-viewport-trinity")

    def test_acquisition_smoke_inventory(self):
        targets = iter_marketing_acquisition_smoke_targets()
        paths = {t.path for t in targets}
        self.assertIn("/storefront/", paths)
        for slug in ACQUISITION_PERSONALITY_SLUGS:
            self.assertIn(f"/experience/{slug}/", paths)

    def test_academics_template_viewport(self):
        text = (REPO / "templates/marketing/academics.html").read_text(encoding="utf-8")
        # The morph bundle is a {% static %} argument; the read stays for it alone.
        self.assertIn("mkt-gradebook-morph.js", text)
        assert_markup(self, ACADEMICS, 'data-mkt-personality-page="academics"')

    def test_edge_mesh_drop_simulator(self):
        assert_markup(
            self,
            RUGGED_ENGINE,
            "data-mkt-drop-simulator",
            'data-mkt-network="blackout"',
        )

    def test_personality_pages_verifier(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_personality_pages.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    @unittest.skipUnless(
        shutil.which("ffmpeg"),
        "ffmpeg required: this orchestrator bundles the glocal marketing-loop gate, "
        "which needs ffmpeg to derive real regional loop videos from the hero; without "
        "it only 275B placeholders exist (all other sub-gates pass and have their own "
        "tests), so the aggregate returncode is 1 for an environment reason, not a bug.",
    )
    def test_internal_audit_orchestrator(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_lane2_internal_audit.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("MARKETING_LANE2_INTERNAL_AUDIT_PASS", proc.stdout)
