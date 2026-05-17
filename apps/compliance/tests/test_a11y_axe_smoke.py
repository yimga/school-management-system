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
    # most prone to a11y regressions.
    PUBLIC_ROUTES = [
        "/onboard/",
        "/marketing/",
        "/authentication/login/",
        "/authentication/forgot-password/",
        "/healthz/",
        "/marketing/pricing/",
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

    # Pass 10.C: authenticated-template coverage. Driven by a Selenium session
    # fixture that drops a logged-in cookie so the scan can hit /portal/, the
    # backend dashboards, and any other surface that requires auth. The fixture
    # uses Django's standard test-client session machinery and pipes the
    # session cookie into the Chrome driver.
    # 2026-05-14 wave NS-3: explicit 10-template matrix.
    # 2026-05-16 wave v2.80: widened to 14 authenticated routes — 4 dashboard
    # shells + finance/students + people + studio_os + super (control plane) +
    # app catalog (governance + tenant) + at-risk labeling + help center +
    # notifications. Each shell + each high-traffic CRUD surface gets scanned.
    # 2026-05-17 wave v3.18: 18 authenticated routes — adds 4 explicit
    # manager.runmycampus.com surfaces that the 12-pillar audit (P2)
    # flagged as not in axe coverage. In CI these resolve through the
    # default URL conf; in production they are served from the dedicated
    # manager subdomain via `config.manager_urls`. The same templates
    # render in both, so axe-on-default-conf is the authoritative gate.
    AUTH_ROUTES = [
        "/portal/",
        "/portal/teacher/",
        "/portal/parent/",
        "/backend/",
        "/portal/finance/invoices/",
        "/portal/configure/",
        "/studio/",
        "/super/",                                # manager: control plane home
        "/super/marketplace-app-catalog/",        # manager: marketplace
        "/super/feature-control/",                # manager: feature-flag control panel
        "/super/operator-console/",               # manager: operator console
        "/super/configuration-center/",           # manager: tenant config hub
        "/super/security-surface/",               # manager: security posture
        "/portal/marketplace/app-catalog/",
        "/portal/notifications/",
        "/help/",
        "/portal/at-risk/labeling/",
        "/release-notes/",
    ]

    def _login_via_session(self):
        """
        Create a superuser, build a Django session, then drop that session
        cookie into the live Chrome driver. Returns the user for downstream
        tests that need it.
        """
        from importlib import import_module

        from django.conf import settings as dj_settings
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(
            username="axe_test_super",
            email="axe@runmycampus.test",
            password="Test1234!",
        )
        engine = import_module(dj_settings.SESSION_ENGINE)
        session = engine.SessionStore()
        session["_auth_user_id"] = str(user.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session.save()
        # Visit the live server once so we can set a cookie on its origin.
        self.driver.get(self.live_server_url + "/healthz/")
        self.driver.add_cookie(
            {
                "name": dj_settings.SESSION_COOKIE_NAME,
                "value": session.session_key,
                "path": "/",
            }
        )
        return user

    def test_authenticated_routes_have_no_severe_violations(self):
        self._login_via_session()
        failures = []
        for path in self.AUTH_ROUTES:
            try:
                results = self._axe_scan(path)
            except Exception as exc:  # noqa: BLE001
                failures.append((path, f"scan_failed: {exc}"))
                continue
            severe = self._filter_severe(results)
            if severe:
                failures.append((path, json.dumps(severe, indent=2)[:2000]))
        if failures:
            self.fail(
                "axe-core flagged severe violations on authenticated routes:\n\n"
                + "\n\n".join(f"-- {path} --\n{detail}" for path, detail in failures)
            )
