"""
Certification: demo mode flags, context processor, portal shell markers (closing slice).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from django.test import RequestFactory, TestCase, override_settings

from apps.platform_runtime.context_processors import demo_sandbox_banner


class DemoModeSettingsResolutionTests(TestCase):
    """RUNMYCAMPUS_DEMO_ENABLED is derived in config.settings from sandbox/mode env-style flags."""

    def test_context_processor_reflects_runmycampus_demo_enabled(self):
        req = RequestFactory().get("/")
        with override_settings(RUNMYCAMPUS_DEMO_ENABLED=True, RUNMYCAMPUS_DEMO_MODE=False):
            ctx = demo_sandbox_banner(req)
            self.assertTrue(ctx["runmycampus_demo_sandbox"])
            self.assertTrue(ctx["runmycampus_demo_enabled"])
            self.assertFalse(ctx["runmycampus_demo_mode"])
        with override_settings(
            RUNMYCAMPUS_DEMO_ENABLED=False,
            RUNMYCAMPUS_DEMO_MODE=False,
        ):
            ctx = demo_sandbox_banner(req)
            self.assertFalse(ctx["runmycampus_demo_sandbox"])
            self.assertFalse(ctx["runmycampus_demo_enabled"])

    def test_subprocess_demo_mode_env_enables_unified_flag(self):
        """DEMO_MODE=1 (no sandbox) sets RUNMYCAMPUS_DEMO_MODE and RUNMYCAMPUS_DEMO_ENABLED (fresh interpreter)."""
        root = Path(__file__).resolve().parents[3]
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        env["DEMO_MODE"] = "1"
        for k in (
            "RUNMYCAMPUS_DEMO_SANDBOX",
            "RUNMYCAMPUS_DEMO_MODE",
            "RUNMYCAMPUS_DEMO_ENABLED",
        ):
            env.pop(k, None)
        code = (
            "import django\n"
            "django.setup()\n"
            "from django.conf import settings\n"
            "assert settings.RUNMYCAMPUS_DEMO_MODE is True, settings.RUNMYCAMPUS_DEMO_MODE\n"
            "assert settings.RUNMYCAMPUS_DEMO_ENABLED is True\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)


class DemoPortalShellMarkersTests(TestCase):
    """Banner + guided hints render only when demo is enabled (portal_base contract)."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User

        cls.staff = User.objects.create_user(
            username="demo_shell_staff",
            password="cert-pass-01",
            is_staff=True,
        )
        cls.staff.role = User.Role.ADMIN
        cls.staff.save(update_fields=["role"])

    @override_settings(RUNMYCAMPUS_DEMO_ENABLED=True, RUNMYCAMPUS_DEMO_MODE=False)
    def test_demo_banner_and_hints_when_enabled(self):
        from django.urls import reverse

        self.client.login(username="demo_shell_staff", password="cert-pass-01")
        url = reverse("accounts:user_notifications")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-rmc-demo-sandbox-banner="1"')
        self.assertContains(r, "data-rmc-demo-guided-hints")

    @override_settings(RUNMYCAMPUS_DEMO_ENABLED=False)
    def test_no_demo_banner_when_disabled(self):
        from django.urls import reverse

        self.client.login(username="demo_shell_staff", password="cert-pass-01")
        r = self.client.get(reverse("accounts:user_notifications"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'data-rmc-demo-sandbox-banner="1"')


class MobileLuxuryCssContractTests(TestCase):
    """mobile-luxury-surfaces.css linked exactly once on portal shell."""

    def test_portal_base_links_mobile_luxury_once(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "templates" / "portal_base.html").read_text(
            encoding="utf-8", errors="replace"
        )
        n = text.count("mobile-luxury-surfaces.css")
        self.assertEqual(
            n,
            1,
            msg="portal_base must load mobile-luxury-surfaces.css exactly once",
        )

    def test_mobile_luxury_css_scroll_and_touch_rules(self):
        root = Path(__file__).resolve().parents[3]
        css = (root / "static" / "css" / "mobile-luxury-surfaces.css").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("-webkit-overflow-scrolling: touch", css)
        self.assertIn("min-height: 44px", css)
