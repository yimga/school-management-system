"""
Pass 10: axe-core accessibility smoke test scaffold.

This test is opt-in — it only runs when:
  * `selenium` and `axe-selenium-python` are importable, AND
  * the environment variable RUN_A11Y_TESTS=1 is set.

Otherwise it is skipped, so it cannot redden unrelated CI runs. Once a Chromium
runner is wired into CI (with `chromedriver` on PATH), set RUN_A11Y_TESTS=1 to
get a hard fail on any new WCAG 2.1 AA serious/critical violation on the homepage.

Pass 10.B will widen this to the 10 highest-traffic templates (portal_base,
control_plane_base, finance/invoices, evals/evaluation_admin, …).
"""

from __future__ import annotations

import json
import os
import unittest

from django.test import LiveServerTestCase

RUN_A11Y_TESTS = os.environ.get("RUN_A11Y_TESTS") == "1"


def _imports_available() -> bool:
    try:
        import selenium  # noqa: F401
        from axe_selenium_python import Axe  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(
    RUN_A11Y_TESTS and _imports_available(),
    "Set RUN_A11Y_TESTS=1 and install selenium + axe-selenium-python to enable.",
)
class HomepageAxeSmokeTests(LiveServerTestCase):
    """Smoke test: marketing landing must have zero serious / critical axe violations."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1366,900")
        cls.driver = webdriver.Chrome(options=opts)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.driver.quit()
        finally:
            super().tearDownClass()

    def _axe_scan(self, path: str) -> dict:
        from axe_selenium_python import Axe

        self.driver.get(f"{self.live_server_url}{path}")
        axe = Axe(self.driver)
        axe.inject()
        return axe.run()

    def _filter_severe(self, results: dict) -> list[dict]:
        violations = results.get("violations") or []
        return [v for v in violations if v.get("impact") in ("serious", "critical")]

    def test_homepage_has_no_severe_violations(self):
        results = self._axe_scan("/")
        severe = self._filter_severe(results)
        if severe:
            self.fail(
                "axe-core found serious/critical violations on /:\n"
                + json.dumps(severe, indent=2)[:4000]
            )

    # Pass 10.B: widened scan. These routes are unauthenticated entry points
    # — they don't need fixtures and they hit the headers / footers / forms
    # most prone to a11y regressions. Authenticated coverage (portal_base,
    # backend_base, finance/invoices, evals/evaluation_admin) lands when a
    # fixture-based session helper is wired up — separate change.
    PUBLIC_ROUTES = [
        "/onboard/",
        "/marketing/",
        "/authentication/login/",
        "/healthz/",
    ]

    def test_public_routes_have_no_severe_violations(self):
        failures = []
        for path in self.PUBLIC_ROUTES:
            try:
                results = self._axe_scan(path)
            except Exception as exc:  # noqa: BLE001 - route may 404; record + continue
                failures.append((path, f"scan_failed: {exc}"))
                continue
            severe = self._filter_severe(results)
            if severe:
                failures.append((path, json.dumps(severe, indent=2)[:2000]))
        if failures:
            self.fail(
                "axe-core flagged severe violations on:\n\n"
                + "\n\n".join(f"-- {path} --\n{detail}" for path, detail in failures)
            )
