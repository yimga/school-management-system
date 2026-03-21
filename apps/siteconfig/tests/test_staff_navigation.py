"""Site settings URL resolution: manager → super; tenant → admin; platform URLConf → super fallback."""

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.staff_navigation import (
    site_settings_change_url,
    site_settings_list_url,
)


class StaffNavigationUrlTests(SimpleTestCase):
    def test_manager_request_uses_super_list(self):
        rf = RequestFactory()
        req = rf.get("/super/")
        req.public_host_kind = "manager"
        url = site_settings_list_url(req)
        self.assertEqual(url, reverse("super:site_settings_list"))

    def test_manager_request_uses_super_edit(self):
        rf = RequestFactory()
        req = rf.get("/super/")
        req.public_host_kind = "manager"
        url = site_settings_change_url(req, 42)
        self.assertEqual(url, reverse("super:site_settings_edit", kwargs={"pk": 42}))

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_tenant_urlconf_uses_admin_when_available(self):
        rf = RequestFactory()
        req = rf.get("/admin/")
        req.public_host_kind = "tenant"
        url = site_settings_list_url(req)
        self.assertEqual(url, reverse("admin:siteconfig_sitesettings_changelist"))

    def test_platform_root_conf_has_no_site_settings_admin_reverse(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:siteconfig_sitesettings_changelist")
        # Fallback list still works for operators
        self.assertEqual(
            site_settings_list_url(None), reverse("super:site_settings_list")
        )
