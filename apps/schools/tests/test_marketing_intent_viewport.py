"""RUNMYCAMPUS-SURGICAL-REFIT — marketing intent viewport + sandbox compliance."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

from apps.schools.marketing_media_matrix import VALID_SANDBOX_MODULES
from apps.schools.views_marketing_api import _validate_sandbox_payload

REPO = Path(__file__).resolve().parents[3]


class MarketingIntentViewportTests(SimpleTestCase):
    def test_personality_sections_viewport_locked(self):
        for partial in (
            "_hero_speed_duel.html",
            "_zero_ui_lab.html",
            "_viewport_trinity.html",
            "_enterprise_constellation.html",
            "_sovereign_kernel.html",
            "_clinical_ledger.html",
            "_rugged_engine.html",
        ):
            text = (REPO / "templates/marketing/partials/sections" / partial).read_text(
                encoding="utf-8"
            )
            self.assertIn("mkt-ve-section--viewport-lock", text, partial)
            self.assertIn('data-mkt-scroll-policy="viewport-lock"', text, partial)

    def test_base_marketing_geo_lang_dir(self):
        base = (REPO / "templates/marketing/base_marketing.html").read_text(encoding="utf-8")
        self.assertIn("geo.locale", base)
        self.assertIn("geo.direction", base)

    def test_sandbox_wizard_modules_match_backend(self):
        sovereign = (
            REPO / "templates/marketing/partials/sections/_sovereign_kernel.html"
        ).read_text(encoding="utf-8")
        for key in ("finance", "offline", "communications", "starter_stack"):
            self.assertIn(f'value="{key}"', sovereign)
            self.assertIn(key, VALID_SANDBOX_MODULES)

    def test_sandbox_validate_rejects_unknown_module(self):
        ok, msg, _steps = _validate_sandbox_payload(
            {"region": "US", "school_size": "small", "modules": ["not_a_real_module"]}
        )
        self.assertFalse(ok)
        self.assertIn("module", msg.lower())

    def test_lane2_external_honesty_gate(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_lane2_external_honesty.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_text_token_alias_registered(self):
        from apps.schools.templatetags import marketing_media

        self.assertTrue(hasattr(marketing_media, "text_token"))

    def test_homepage_template_exists(self):
        path = REPO / "templates/marketing/homepage.html"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("mkt-intent-home__stack", text)

    def test_copy_registry_sa_arabic_headline(self):
        from apps.schools.marketing_media_matrix import (
            MARKETING_COPY_REGISTRY,
            marketing_copy_token,
        )

        headline = marketing_copy_token("SA", "txt_hero_headline", {})
        self.assertIn("نظام", headline)
        self.assertIn("txt_hero_headline", MARKETING_COPY_REGISTRY["US"])

    def test_geo_context_includes_apm_image(self):
        from apps.schools.marketing_geo_context import build_geo_context

        class _Req:
            META = {"HTTP_ACCEPT_LANGUAGE": "en-US"}
            COOKIES = {}

        geo = build_geo_context(_Req())
        self.assertTrue(geo.get("apm_image"))

    def test_intent_homepage_optin_gate(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_intent_homepage_optin.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("MARKETING_INTENT_HOMEPAGE_OPTIN_PASS", proc.stdout)
