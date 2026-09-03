"""One Record Scroll — /storefront/ wiring and production template contract."""

from __future__ import annotations

from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.siteconfig.tests._template_nodes import (
    assert_loads_static,
    assert_wires,
)

_TN_ROOT = Path(__file__).resolve().parents[3]

REPO = Path(__file__).resolve().parents[3]


class OneRecordScrollTemplateTests(SimpleTestCase):
    def test_homepage_includes_one_record_scroll_partial(self):
        text = (REPO / "templates/marketing/homepage.html").read_text(encoding="utf-8")
        self.assertIn("_one_record_scroll.html", text)
        self.assertIn("mkt-one-record-scroll.js", text)
        self.assertIn("mkt-one-record-scroll.css", text)
        # All three needles survive a commented-out homepage. Ask the engine:
        # the include is a node and the two assets are {% static %} tags.
        assert_wires(self, _TN_ROOT / "templates/marketing/homepage.html",
                     "_one_record_scroll.html")
        assert_loads_static(self, _TN_ROOT / "templates/marketing/homepage.html",
                            "mkt-one-record-scroll.js", "mkt-one-record-scroll.css")

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

    def test_threshold_era_deprecated_preview_route(self):
        views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
        self.assertIn("marketing_threshold_era_preview", views)
        self.assertIn("threshold_era_home.html", views)
        self.assertIn("noindex", views)
        urls = (REPO / "config/urls.py").read_text(encoding="utf-8")
        self.assertIn("experience/threshold-era/", urls)
        self.assertIn("marketing_intent_homepage", urls)

    def test_marketing_landing_prefers_intent_over_threshold_when_opted_in(self):
        views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
        chunk = views.split("def marketing_landing", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("MARKETING_THRESHOLD_ERA_ENABLED", chunk)
        self.assertIn("MARKETING_INTENT_HOMEPAGE", chunk)
        self.assertIn("marketing/homepage.html", chunk)
        self.assertLess(
            chunk.index("MARKETING_THRESHOLD_ERA_ENABLED"),
            chunk.index("MARKETING_INTENT_HOMEPAGE"),
        )

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
