"""Platform brand mark and manager header regression tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase, override_settings

from apps.test_utils.http_clients import login_manager_client

User = get_user_model()

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR, "*"],
    ROOT_URLCONF="config.manager_urls",
)
class PlatformBrandHeaderTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="brand_header_admin",
            password="x" * 12,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def test_platform_wordmark_partial_renders_navy_gold_split(self):
        html = render_to_string(
            "components/rmc_brand_mark.html",
            {
                "wordmark_style": "platform",
                "variant": "lockup",
                "size": 32,
                "label": "RunMyCampus",
                "surface_badge": "Manager",
                # The partial reads SITE.site_name (normally injected by the
                # site_settings context processor) in its label/monogram defaults;
                # render_to_string without a request runs no processors, so supply it.
                "SITE": {"site_name": "RunMyCampus"},
            },
        )
        self.assertIn('data-rmc-brand-mark="1"', html)
        self.assertIn("rmc-brand-mark__title--platform", html)
        self.assertIn("rmc-brand-word--navy", html)
        self.assertIn("rmc-brand-word--gold", html)
        self.assertIn("RUN", html)
        self.assertIn("MY", html)
        self.assertIn("CAMPUS", html)

    def test_manager_super_dashboard_renders_platform_brand_markers(self):
        # /super/ on the manager host is MFA-gated (SUPERADMIN is a baseline-MFA
        # role) — arm a confirmed device + verified operator session, or the request
        # bounces (302) to /authentication/mfa/…, never reaching the dashboard.
        client = login_manager_client(self.user, password="x" * 12, host=_MGR)
        response = client.get("/super/")
        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-brand-mark="1"', body)
        self.assertIn("rmc-brand-mark__title--platform", body)
        self.assertIn("rmc-brand-word--navy", body)
        self.assertIn("rmc-brand-word--gold", body)
        self.assertIn('data-rmc-platform-header="manager"', body)
        self.assertIn("rmc-control-plane-chrome", body)
        self.assertIn("cpSearchInput", body)
        self.assertIn("runmycampus-logo-mark.svg", body)
        self.assertNotIn("runmycampus-logo-mark.png", body)

    def test_legacy_png_logo_env_resolves_to_svg(self):
        from apps.siteconfig.context_processors import _resolve_public_brand_logo_url

        resolved = _resolve_public_brand_logo_url(
            "/static/images/brand/runmycampus-logo-mark.png",
            default_static="images/brand/runmycampus-logo-mark.svg",
        )
        self.assertIn("runmycampus-logo-mark.svg", resolved)
        self.assertNotIn(".png", resolved)