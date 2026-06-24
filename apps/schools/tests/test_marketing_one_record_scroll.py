"""One Record Scroll — /storefront/ wiring and production template contract."""

from __future__ import annotations

from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

REPO = Path(__file__).resolve().parents[3]


class OneRecordScrollTemplateTests(SimpleTestCase):
    def test_homepage_includes_one_record_scroll_partial(self):
        text = (REPO / "templates/marketing/homepage.html").read_text(encoding="utf-8")
        self.assertIn("_one_record_scroll.html", text)
        self.assertIn("mkt-one-record-scroll.js", text)
        self.assertIn("mkt-one-record-scroll.css", text)

    def test_one_record_scroll_partial_has_six_chapters(self):
        text = (
            REPO / "templates/marketing/partials/sections/_one_record_scroll.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-mkt-one-record-scroll", text)
        self.assertEqual(text.count("data-mkt-or-panel="), 6)
        for panel in (
            "panel-run",
            "panel-sov",
            "panel-teach",
            "panel-pay",
            "panel-govern",
            "panel-grow",
        ):
            self.assertIn(panel, text)

    def test_stage_partials_exist(self):
        stage_dir = REPO / "templates/marketing/partials/one_record_scroll"
        for name in (
            "_stage_speed_duel.html",
            "_stage_sovereign_wizard.html",
            "_stage_fluid_gradebook.html",
            "_stage_clinical_ledger.html",
            "_stage_rugged_console.html",
            "_stage_simulations_hub.html",
        ):
            self.assertTrue((stage_dir / name).is_file(), name)

    def test_scroll_js_uses_midpoint_spy_and_force_click(self):
        js = (REPO / "static/marketing/js/mkt-one-record-scroll.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("pickByMidpoint", js)
        self.assertIn("force: true", js)
        self.assertIn("data-mkt-one-record-scroll", js)

    def test_verify_one_record_scroll_gate(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_marketing_one_record_scroll.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("ONE_RECORD_SCROLL_PASS", proc.stdout)


@override_settings(ALLOWED_HOSTS=["testserver", "runmycampus.com"])
class OneRecordScrollHttpTests(TestCase):
    def test_storefront_renders_one_record_scroll(self):
        client = Client(HTTP_HOST="runmycampus.com")
        url = reverse("marketing_intent_homepage")
        self.assertEqual(url, "/storefront/")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("data-mkt-one-record-scroll", content)
        self.assertIn("panel-run", content)
        self.assertIn("data-mkt-speed-duel", content)

    def test_threshold_era_preview_is_noindex(self):
        client = Client(HTTP_HOST="runmycampus.com")
        url = reverse("marketing_threshold_era_preview")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response.get("X-Robots-Tag", "").lower())
        self.assertIn("threshold_era_home", str(response.template_name))

    @override_settings(MARKETING_THRESHOLD_ERA_ENABLED=False, MARKETING_INTENT_HOMEPAGE=True)
    def test_marketing_landing_prefers_intent_not_threshold(self):
        client = Client(HTTP_HOST="runmycampus.com")
        from apps.schools.marketing_views import marketing_landing

        response = marketing_landing(client.get("/").wsgi_request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("marketing/homepage.html", response.template_name)
