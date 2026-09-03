"""SOVEREIGN-MULTI-PERSONALITY layout token matrix tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.layout_personality_matrix import (
    PERSONALITY_CLINICAL,
    PERSONALITY_SOVEREIGN,
    resolve_personality_os,
)
from apps.platform_runtime.regional_surface_tokens import regional_surface_token
from apps.platform_runtime.shell_contract import resolve_shell_dataclass
from apps.siteconfig.tests._template_nodes import assert_markup

REPO = Path(__file__).resolve().parents[3]

SHELL_HTML_ATTRS = REPO / "templates/partials/shell_rmc_registry_html_attrs.html"
WIZARD_VIEWPORT = REPO / "templates/components/rmc_setup_wizard_viewport.html"


class LayoutPersonalityMatrixTests(SimpleTestCase):
    def test_route_family_personality_mapping(self):
        self.assertEqual(resolve_personality_os("admin"), PERSONALITY_SOVEREIGN)
        self.assertEqual(resolve_personality_os("billing"), PERSONALITY_CLINICAL)
        self.assertEqual(resolve_personality_os("academics"), "fluid")

    def test_regional_compliance_hub_gb(self):
        ctx = {"brand": {"country_code": "GB"}}
        self.assertIn("Ofsted", regional_surface_token(ctx, "txt_compliance_hub") or "")

    def test_text_token_tag_resolves_regional(self):
        tpl = Template(
            "{% load rmc_layout_tokens %}{% text_token 'txt_compliance_hub' %}"
        )
        req = RequestFactory().get("/")
        req.geo_context = {"country_code": "GB"}
        out = tpl.render(Context({"request": req}))
        self.assertIn("Ofsted", out)

    def test_shell_html_attrs_include_personality_os(self):
        # This partial exists only to EMIT attributes onto <html>. Reading its
        # bytes cannot tell an emitted attribute from one inside {% comment %},
        # and a commented-out one puts nothing on the element -- every selector
        # and every bit of JS keyed to the personality would then miss.
        assert_markup(
            self,
            SHELL_HTML_ATTRS,
            "data-rmc-personality-os",
            "data-rmc-iso-viewport-lock",
        )

    def test_wizard_viewport_component_exists(self):
        path = REPO / "templates/components/rmc_setup_wizard_viewport.html"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        # is_file() only says the component is on disk. Whether it is a viewport
        # is a question about what it emits, so the engine answers that half.
        assert_markup(
            self,
            WIZARD_VIEWPORT,
            "data-rmc-wizard-viewport",
            "viewport-lock",
        )
        self.assertIn("data-rmc-wizard-viewport", text)
        self.assertIn("viewport-lock", text)

    def test_admin_path_personality_on_contract(self):
        req = RequestFactory().get("/admin/")
        req.public_host_kind = "school"
        c = resolve_shell_dataclass(req)
        self.assertEqual(c.personality_os, PERSONALITY_SOVEREIGN)

    def test_sovereign_layout_verifier(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_sovereign_layout_token_matrix.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
            # Windows text=True defaults to cp1252 and crashes decoding the
            # verifier's UTF-8 output (em-dashes / smart quotes); force UTF-8.
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
