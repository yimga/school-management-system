from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.schools.models import School
from apps.siteconfig.admin_navigation_preferences import (
    AdminNavigationPreferenceService,
    MAX_PINNED_ITEMS,
    _scope_key,
    admin_navigation_preferences_view,
    build_admin_navigation_contract,
)
from config.admin import platform_admin_site, tenant_admin_site


ROOT = Path(__file__).resolve().parents[3]


class AdminNavigationPreferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="admin-navigation-test",
            email="admin-navigation@example.test",
            password="test-only-password",
        )
        cls.school = School.objects.create(
            name="Navigation Test School",
            slug="navigation-test",
            subdomain="navigation-test",
            country_code="CM",
            is_active=True,
        )
        cls.other_user = get_user_model().objects.create_superuser(
            username="admin-navigation-other-user",
            email="admin-navigation-other@example.test",
            password="test-only-password",
        )

    def _request(self, *, host="navigation-test.runmycampus.com", method="get", payload=None):
        factory = RequestFactory()
        if method == "post":
            request = factory.post(
                "/admin/navigation-preferences/",
                data=json.dumps(payload if payload is not None else {}),
                content_type="application/json",
                HTTP_HOST=host,
            )
        else:
            request = factory.get(
                "/admin/navigation-preferences/", HTTP_HOST=host
            )
        request.user = self.user
        request.school = self.school
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        SessionMiddleware(lambda current_request: None).process_request(request)
        return request

    def test_preferences_are_isolated_by_hostname_and_admin_site(self):
        tenant_scope = _scope_key(
            host="navigation-test.runmycampus.com", admin_site_name="tenant_admin"
        )
        other_tenant_scope = _scope_key(
            host="other-school.runmycampus.com", admin_site_name="tenant_admin"
        )
        operator_scope = _scope_key(
            host="manager.runmycampus.com", admin_site_name="admin"
        )
        saved = AdminNavigationPreferenceService.write(
            user=self.user,
            scope_key=tenant_scope,
            state={
                "pinned": [{"path": "/admin/academics/academicyear/", "label": "Academic years"}],
                "recent": [],
                "compact": True,
                "advancedOpen": True,
                "appsOpen": False,
            },
        )
        self.assertTrue(saved["compact"])
        self.assertEqual(
            AdminNavigationPreferenceService.read(
                user=self.user, scope_key=tenant_scope
            )["pinned"][0]["label"],
            "Academic years",
        )
        self.assertEqual(
            AdminNavigationPreferenceService.read(
                user=self.user, scope_key=other_tenant_scope
            )["pinned"],
            [],
        )
        self.assertEqual(
            AdminNavigationPreferenceService.read(
                user=self.user, scope_key=operator_scope
            )["pinned"],
            [],
        )
        self.assertEqual(
            AdminNavigationPreferenceService.read(
                user=self.other_user, scope_key=tenant_scope
            )["pinned"],
            [],
        )

    def test_endpoint_round_trip_and_contract_uses_tenant_namespace(self):
        preferences = {
            "pinned": [{"path": "/admin/people/studentprofile/", "label": "Students"}],
            "recent": [{"path": "/admin/academics/term/?active=1", "label": "Active terms"}],
            "compact": False,
            "advancedOpen": True,
            "appsOpen": True,
        }
        response = admin_navigation_preferences_view(
            self._request(method="post", payload={"preferences": preferences}),
            admin_site=tenant_admin_site,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["preferences"], preferences)

        request = self._request()
        contract = build_admin_navigation_contract(request, tenant_admin_site)
        self.assertEqual(contract["preferences"], preferences)
        self.assertEqual(contract["endpoint"], "/admin/navigation-preferences/")
        self.assertTrue(contract["scope"].startswith("nav-"))
        other_request = self._request()
        other_request.user = self.other_user
        self.assertNotEqual(
            contract["scope"],
            build_admin_navigation_contract(other_request, tenant_admin_site)["scope"],
        )

    def test_invalid_external_paths_unknown_keys_and_limits_fail_closed(self):
        base = {
            "recent": [], "compact": False, "advancedOpen": False, "appsOpen": False,
        }
        for preferences in (
            {**base, "pinned": [{"path": "https://evil.test/admin/", "label": "Evil"}]},
            {**base, "pinned": [], "unexpected": True},
            {
                **base,
                "pinned": [
                    {"path": f"/admin/example/model/{index}/", "label": f"Page {index}"}
                    for index in range(MAX_PINNED_ITEMS + 1)
                ],
            },
        ):
            response = admin_navigation_preferences_view(
                self._request(method="post", payload={"preferences": preferences}),
                admin_site=tenant_admin_site,
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(json.loads(response.content)["ok"])

    def test_operator_and_tenant_sites_expose_separate_endpoints(self):
        tenant = build_admin_navigation_contract(self._request(), tenant_admin_site)
        operator_request = self._request(host="manager.runmycampus.com")
        operator_request.school = None
        operator_request.public_host_kind = "manager"
        operator_request.urlconf = "config.manager_urls"
        operator = build_admin_navigation_contract(operator_request, platform_admin_site)
        self.assertEqual(tenant["endpoint"], "/admin/navigation-preferences/")
        self.assertEqual(operator["endpoint"], "/admin/navigation-preferences/")
        self.assertNotEqual(tenant["scope"], operator["scope"])

    def test_tenant_sidebar_runtime_owns_server_sync_search_and_active_app(self):
        javascript = (ROOT / "static/js/rmc-tenant-admin-sidebar-v2.js").read_text(
            encoding="utf-8"
        )
        template = (ROOT / "templates/admin/app_list.html").read_text(
            encoding="utf-8"
        )
        sidebar = (ROOT / "templates/admin/sidebar_inner.html").read_text(
            encoding="utf-8"
        )
        base = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
        for token in (
            "rmcAdminNavigationContract",
            "rmc-admin-navigation-pending-v1:",
            'method: "POST"',
            "Pinned is full",
            "data-rmc-admin-search-empty",
        ):
            self.assertIn(token, javascript + template + sidebar)
        self.assertIn("getAdminAppsState", template)
        self.assertIn("data-admin-search=", template)
        self.assertNotIn("runmycampus-admin-pinned", base)
        self.assertNotIn("admin-qa-setup-advanced", template)
