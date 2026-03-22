"""
Host profile wiring: tenant urlconf vs manager urlconf.

Ensures navigation-critical names reverse on the correct plane (SOT: platform boundary;
Studio OS deep_links; control_plane_nav). Fails fast if a link is staged in templates but
missing from the active URLconf.
"""

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.schools.host_profile_url_matrix import (
    MANAGER_HOST_CRITICAL_VIEWS,
    MANAGER_ONLY_VIEW_PREFIXES,
    TENANT_HOST_CRITICAL_VIEWS,
)


class TenantHostProfileUrlWiringTests(SimpleTestCase):
    """Every TENANT_HOST_CRITICAL_VIEWS must reverse under config.tenant_urls."""

    def test_tenant_critical_views_resolve(self):
        for viewname in TENANT_HOST_CRITICAL_VIEWS:
            with self.subTest(viewname=viewname):
                url = reverse(viewname, urlconf="config.tenant_urls")
                self.assertTrue(url.startswith("/"), msg=viewname)

    def test_super_views_do_not_resolve_on_tenant_urlconf(self):
        from apps.studio_os.tests.test_studio_rail_resolution import (
            _STUDIO_RAIL_VIEWNAMES,
        )

        for viewname in _STUDIO_RAIL_VIEWNAMES:
            if any(viewname.startswith(p) for p in MANAGER_ONLY_VIEW_PREFIXES):
                with self.subTest(viewname=viewname):
                    with self.assertRaises(NoReverseMatch):
                        reverse(viewname, urlconf="config.tenant_urls")


class ManagerHostProfileUrlWiringTests(SimpleTestCase):
    """Every MANAGER_HOST_CRITICAL_VIEWS must reverse under config.manager_urls."""

    def test_manager_critical_views_resolve(self):
        for viewname in MANAGER_HOST_CRITICAL_VIEWS:
            with self.subTest(viewname=viewname):
                url = reverse(viewname, urlconf="config.manager_urls")
                self.assertTrue(url.startswith("/"), msg=viewname)

    def test_super_views_resolve_on_manager_urlconf(self):
        for viewname in ("super:dashboard", "super:admin_bridge"):
            with self.subTest(viewname=viewname):
                if viewname == "super:admin_bridge":
                    url = reverse(
                        viewname,
                        kwargs={"bridge_key": "integrations"},
                        urlconf="config.manager_urls",
                    )
                else:
                    url = reverse(viewname, urlconf="config.manager_urls")
                self.assertIn("/super/", url)
