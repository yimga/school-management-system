"""HTTP contract tests for Wedge 22 multi-campus rollup surfaces (control plane)."""

from __future__ import annotations

import json
import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.tests.manager_client import login_manager_control_plane
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School


_ALLOWED_HOSTS = ["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
_MANAGER_HOST = "manager.runmycampus.com"
_WEDGE_QS = "?wedge=22"
_PASSWORD = "passwordxx"


@override_settings(
    ALLOWED_HOSTS=_ALLOWED_HOSTS,
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class MulticampusWedgeHttpTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username=f"mcw_{uuid.uuid4().hex[:8]}",
            password=_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        plan = Plan.objects.create(
            name="McPlan",
            slug=f"mc-plan-{uuid.uuid4().hex[:8]}",
            included_features=["core"],
            is_active=True,
        )
        region = RegionConfig.objects.create(
            code=f"M{uuid.uuid4().hex[:6].upper()}",
            name="McRegion",
            timezone="UTC",
            default_currency="USD",
        )
        cls.parent = School.objects.create(
            name="Metro Group",
            slug=f"metro-{uuid.uuid4().hex[:6]}",
            subdomain=f"metro-{uuid.uuid4().hex[:6]}",
            is_active=True,
            plan=plan,
            default_region=region,
        )
        cls.child = School.objects.create(
            name="North Campus",
            slug=f"north-{uuid.uuid4().hex[:6]}",
            subdomain=f"north-{uuid.uuid4().hex[:6]}",
            parent_school=cls.parent,
            is_active=True,
            plan=plan,
            default_region=region,
        )

    def _staff_client(self) -> Client:
        client = Client(HTTP_HOST=_MANAGER_HOST)
        login_manager_control_plane(
            client,
            self.staff,
            password=_PASSWORD,
            host=_MANAGER_HOST,
        )
        return client

    def _url(self, name: str) -> str:
        return reverse(name, urlconf="config.manager_urls")

    def test_billing_surface_200_with_parent_filter(self):
        client = self._staff_client()
        url = (
            self._url("super:wedge_surface_multicampus_billing")
            + _WEDGE_QS
            + f"&parent={self.parent.pk}"
        )
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Multi-campus", body)
        self.assertIn("Metro Group", body)

    def test_billing_json_lists_child_school(self):
        client = self._staff_client()
        url = (
            self._url("super:wedge_surface_multicampus_billing")
            + _WEDGE_QS
            + f"&parent={self.parent.pk}&format=json"
        )
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode("utf-8"))
        names = [row.get("name") for row in (payload.get("tree") or {}).get("children") or []]
        self.assertIn("North Campus", names)

    def test_academics_surface_200(self):
        client = self._staff_client()
        url = self._url("super:wedge_surface_multicampus_academics") + _WEDGE_QS
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Multi-campus group academic rollup", body)

    def test_extension_surface_200(self):
        client = self._staff_client()
        url = self._url("super:wedge_surface_multicampus_extension") + _WEDGE_QS
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Multi-campus group operational rollup", body)

    def test_billing_json_contract(self):
        client = self._staff_client()
        url = (
            self._url("super:wedge_surface_multicampus_billing")
            + _WEDGE_QS
            + "&format=json"
        )
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode("utf-8"))
        self.assertTrue(payload.get("success"))
        self.assertIn("tree", payload)

    def test_anonymous_redirects_to_login(self):
        client = Client(HTTP_HOST=_MANAGER_HOST)
        url = self._url("super:wedge_surface_multicampus_billing") + _WEDGE_QS
        resp = client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/login", resp.headers.get("Location", ""))
