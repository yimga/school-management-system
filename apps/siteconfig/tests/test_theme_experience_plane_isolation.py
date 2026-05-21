"""Dual-plane theme builder isolation — operator vs tenant storage and access."""

from __future__ import annotations

import json
import uuid

from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.platform_runtime.models import RuntimeDefaults
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.theme_builder import (
    OPERATOR_RUNTIME_PAYLOAD_KEY,
    TENANT_SCHOOL_SETTINGS_KEY,
    default_layout,
)
from apps.test_utils.http_clients import login_manager_client, login_tenant_client

_TENANT_SETTINGS = dict(
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)
_MANAGER_SETTINGS = dict(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)


class ThemeExperiencePlaneIsolationTests(TransactionTestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:8]
        self.tenant_host = f"plane-school-{suffix}.runmycampus.com"
        self.school = School.objects.create(
            name="Plane Isolation School",
            slug=f"plane-school-{suffix}",
            subdomain=f"plane-school-{suffix}",
            is_active=True,
        )
        self.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.tenant_admin = User.objects.create_user(
            username=f"plane-admin-{suffix}",
            password="password",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.tenant_admin.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=self.tenant_admin,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        TOTPDevice.objects.update_or_create(
            user=self.tenant_admin,
            name="test-mfa",
            defaults={"confirmed": True},
        )
        self.operator = User.objects.create_superuser(
            username=f"plane-operator-{suffix}",
            password="password",
            email=f"op-{suffix}@example.com",
        )

    @override_settings(**_MANAGER_SETTINGS)
    def test_manager_builder_uses_control_plane_template(self):
        client = login_manager_client(self.operator, password="password")
        response = client.get(reverse("siteconfig:theme_builder"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-plane=\"platform\"", body)
        self.assertIn("Platform operator", body)

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_builder_shows_school_plane_badge(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_builder"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-plane=\"tenant\"")
        self.assertContains(response, "Plane Isolation School")

    @override_settings(**_MANAGER_SETTINGS)
    def test_operator_layout_persists_to_operator_payload_key(self):
        client = login_manager_client(self.operator, password="password")
        url = reverse("siteconfig:theme_builder_layout_api")
        layout = default_layout()
        layout["surface"] = "dark"
        response = client.post(
            url,
            data=json.dumps({"layout": layout}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("plane"), "operator")
        rt = RuntimeDefaults.get_singleton()
        stored = (rt.payload or {}).get(OPERATOR_RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(stored.get("surface"), "dark")

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_layout_persists_to_school_settings(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        url = reverse("siteconfig:theme_builder_layout_api")
        layout = default_layout()
        layout["surface"] = "dark"
        response = client.post(
            url,
            data=json.dumps({"layout": layout}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("plane"), "tenant")
        self.school.refresh_from_db()
        stored = (self.school.settings or {}).get(TENANT_SCHOOL_SETTINGS_KEY) or {}
        self.assertEqual(stored.get("surface"), "dark")

    @override_settings(**_MANAGER_SETTINGS)
    def test_operator_publish_records_operator_publish_log(self):
        client = login_manager_client(self.operator, password="password")
        url = reverse("siteconfig:theme_builder_publish_api")
        response = client.post(
            url,
            data=json.dumps(
                {
                    "layout": default_layout(),
                    "colors": {"primary_color": "#aabbcc"},
                    "publish": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        from apps.siteconfig.theme_builder_plane import OPERATOR_PUBLISH_LOG_KEY

        rt = RuntimeDefaults.get_singleton()
        log = (rt.payload or {}).get(OPERATOR_PUBLISH_LOG_KEY) or []
        self.assertGreaterEqual(len(log), 1)

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_publish_records_school_publish_log(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        url = reverse("siteconfig:theme_builder_publish_api")
        response = client.post(
            url,
            data=json.dumps(
                {
                    "layout": default_layout(),
                    "colors": {"primary_color": "#ddeeff"},
                    "publish": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        from apps.siteconfig.theme_builder_plane import TENANT_PUBLISH_LOG_KEY

        self.school.refresh_from_db()
        log = (self.school.settings or {}).get(TENANT_PUBLISH_LOG_KEY) or []
        self.assertGreaterEqual(len(log), 1)

    @override_settings(**_MANAGER_SETTINGS)
    def test_operator_publish_writes_public_brand_not_tenant_school_settings(self):
        client = login_manager_client(self.operator, password="password")
        url = reverse("siteconfig:theme_builder_publish_api")
        response = client.post(
            url,
            data=json.dumps(
                {
                    "layout": default_layout(),
                    "colors": {"primary_color": "#112233", "accent_color": "#445566"},
                    "publish": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        rt = RuntimeDefaults.get_singleton()
        self.assertEqual(
            getattr(rt, "public_brand_primary_color", None),
            "#112233",
        )
        self.school.refresh_from_db()
        self.assertNotIn(
            TENANT_SCHOOL_SETTINGS_KEY,
            (self.school.settings or {}),
        )

    def test_build_hub_glance_includes_contrast_meta(self):
        from django.test import RequestFactory

        from apps.siteconfig.theme_builder_plane import build_hub_glance_context

        request = RequestFactory().get("/siteconfig/theme-experience/hub/")
        request.user = self.tenant_admin
        request.school = self.school
        glance = build_hub_glance_context(request)
        self.assertIn("contrast_ratio", glance)
        self.assertIn("contrast_ok", glance)
        self.assertIn("contrast_min_ratio", glance)

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_hub_includes_glance_and_fold_nav(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-cp-compact__fold-nav")
        self.assertContains(response, "theme-hub-glance")
        self.assertContains(response, "Brand contrast")
        self.assertContains(response, "rmc-theme-hub-glance__chip")

    @override_settings(**_MANAGER_SETTINGS)
    def test_manager_hub_includes_glance_and_fold_nav(self):
        client = login_manager_client(self.operator, password="password")
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-cp-compact__fold-nav")
        self.assertContains(response, "theme-hub-glance")

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_preview_api_sets_session_overlay(self):
        client = login_tenant_client(
            self.tenant_admin,
            password="password",
            host=self.tenant_host,
        )
        url = reverse("siteconfig:theme_builder_preview_api")
        response = client.post(
            url,
            data=json.dumps(
                {
                    "colors": {"primary_color": "#112233"},
                    "surface": "dark",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("plane"), "tenant")
        from apps.siteconfig.context_processors import SESSION_KEY

        client.session.load()
        overlay = client.session.get(SESSION_KEY) or {}
        self.assertTrue(overlay.get("use_dark_mode"))

    @override_settings(**_MANAGER_SETTINGS)
    def test_operator_rollback_restores_previous_publish(self):
        client = login_manager_client(self.operator, password="password")
        publish_url = reverse("siteconfig:theme_builder_publish_api")
        rollback_url = reverse("siteconfig:theme_builder_rollback_api")
        first = default_layout()
        first["surface"] = "light"
        second = default_layout()
        second["surface"] = "dark"
        for layout in (first, second):
            response = client.post(
                publish_url,
                data=json.dumps(
                    {
                        "layout": layout,
                        "colors": {"primary_color": "#112233"},
                        "publish": True,
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        rollback = client.post(rollback_url, data="{}", content_type="application/json")
        self.assertEqual(rollback.status_code, 200)
        body = rollback.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("layout", {}).get("surface"), "light")
        rt = RuntimeDefaults.get_singleton()
        stored = (rt.payload or {}).get(OPERATOR_RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(stored.get("surface"), "light")

    @override_settings(**_TENANT_SETTINGS)
    def test_tenant_hub_forbidden_on_manager_host_for_tenant_only_user(self):
        """Tenant admin cannot open manager hub (control plane access)."""
        client = login_manager_client(self.tenant_admin, password="password")
        response = client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertIn(response.status_code, (302, 403))
