"""A tenant with no logo must NOT inherit the RunMyCampus platform logo.

Reported bug: a newly created school that never uploaded (or AI-built) a logo showed
the RunMyCampus platform logo in its header as if it were the school's own. The
platform logo belongs to the operator/public surface — a tenant with no logo should
fall back to its own initials / monogram placeholder.

Root cause: ``apps/siteconfig/context_processors.py::site_settings`` defaulted
``SITE_LOGO_URL`` to the platform ``images/logo.png`` and only OVERRODE it for a
tenant when the tenant brand carried a logo — so a no-logo tenant kept the platform
default. Fix: on a tenant surface, blank ``SITE_LOGO_URL`` when the school has no
logo of its own.

Companion: the OPERATOR masthead must ALWAYS render the RunMyCampus mark, even when
``PUBLIC_BRAND_MODE`` is momentarily false (a school bound to the operator request) —
so the operator topbar now passes the platform logo explicitly.
"""

from __future__ import annotations

import os

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.schools.models import School

_HERE = os.path.dirname(os.path.abspath(__file__))
_PORTAL_BASE = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "templates", "portal_base.html")
)
_OPERATOR_TOPBAR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "templates", "partials", "manager_operator_topbar.html")
)


def _tenant_request(school):
    req = RequestFactory().get("/", HTTP_HOST="new-school.runmycampus.com")
    req.user = AnonymousUser()
    req.session = {}
    req.school = school  # _request_school reads request.__dict__["school"]
    req.public_host_kind = None  # tenant subdomain (not base/manager) → not PUBLIC_BRAND_MODE
    return req


class SiteSettingsTenantLogoTests(TestCase):
    def _ctx(self, school):
        from apps.siteconfig.context_processors import site_settings

        return site_settings(_tenant_request(school))

    def test_tenant_without_logo_blanks_site_logo_url(self):
        school = School.objects.create(
            name="New Test High School",
            slug="new-test-high",
            subdomain="new-test-high",
            is_active=True,
        )
        ctx = self._ctx(school)
        # The platform default must NOT leak in as the school's logo.
        self.assertEqual(ctx.get("SITE_LOGO_URL"), "")
        self.assertNotIn("logo.png", ctx.get("SITE_LOGO_URL") or "")

    def test_tenant_with_its_own_logo_keeps_it(self):
        school = School.objects.create(
            name="Branded Academy",
            slug="branded-academy",
            subdomain="branded-academy",
            is_active=True,
            logo_url="https://cdn.example.com/branded/mylogo.png",
        )
        ctx = self._ctx(school)
        self.assertIn("mylogo.png", ctx.get("SITE_LOGO_URL") or "")


class OperatorBrandMarkAlwaysRendersTests(SimpleTestCase):
    """rmc_brand_mark renders a passed-in ``logo_url`` even when PUBLIC_BRAND_MODE is off —
    the mechanism the operator topbar fix relies on."""

    class _Site:
        site_name = "RunMyCampus"

    def test_explicit_logo_url_renders_when_public_brand_mode_off(self):
        html = render_to_string(
            "components/rmc_brand_mark.html",
            {
                "size": 40,
                "variant": "lockup",
                "logo_url": "/static/images/brand/runmycampus-logo-mark.svg",
                "logo_dark_url": "/static/images/brand/runmycampus-logo-mark.svg",
                "PUBLIC_BRAND_MODE": False,  # a school is bound to the operator request
                "SITE": self._Site(),
            },
        )
        self.assertIn("runmycampus-logo-mark.svg", html)
        self.assertIn("rmc-brand-mark__tenant-logo", html)

    def test_without_logo_and_mode_off_falls_to_monogram(self):
        # Contrast: with NO logo_url and PUBLIC_BRAND_MODE off, only the monogram shows —
        # which is exactly why the operator topbar must pass the logo explicitly.
        html = render_to_string(
            "components/rmc_brand_mark.html",
            {"size": 40, "variant": "mark", "PUBLIC_BRAND_MODE": False, "SITE": self._Site()},
        )
        self.assertNotIn("rmc-brand-mark__tenant-logo", html)
        self.assertIn("rmc-brand-mark__glyph", html)

    def test_operator_topbar_passes_platform_logo_to_both_include_sites(self):
        with open(_OPERATOR_TOPBAR, encoding="utf-8") as fh:
            src = fh.read()
        # The platform logo is resolved once and passed to both brand-mark includes.
        self.assertIn("rmc_operator_logo", src)
        self.assertIn("runmycampus-logo-mark.svg", src)
        self.assertEqual(src.count("logo_url=rmc_operator_logo"), 2)


class TenantHeaderSearchWidthPinTests(SimpleTestCase):
    """The header search-width cap must ship in the inline critical pin (stale-cache proof)."""

    def test_search_width_cap_present_in_inline_pin(self):
        with open(_PORTAL_BASE, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("rmc-tenant-chrome-critical", src)
        self.assertIn(".topbar-search.header-search-container", src)
        # Operator-parity cap (rmc-platform-header.css:135/142).
        self.assertIn("min(36rem,48vw)", src)
        self.assertIn("40rem", src)
