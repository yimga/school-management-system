"""Theme builder canvas + layout API (dual-plane storage)."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.siteconfig.theme_builder import (
    OPERATOR_RUNTIME_PAYLOAD_KEY,
    default_layout,
    normalize_layout,
)
from apps.test_utils.http_clients import login_manager_client

_MANAGER_SETTINGS = dict(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)


class ThemeBuilderTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        suffix = uuid.uuid4().hex[:8]
        self.user = User.objects.create_superuser(
            username=f"builder_{suffix}",
            password="Test1234",
            email=f"builder_{suffix}@example.com",
        )
        self.client = login_manager_client(self.user, password="Test1234")

    def test_normalize_layout_keeps_block_order(self):
        raw = {
            "blocks": [
                {"id": "hero", "type": "hero", "enabled": True},
                {"id": "sidebar", "type": "sidebar", "enabled": False},
            ],
            "surface": "dark",
        }
        layout = normalize_layout(raw)
        self.assertEqual(layout["surface"], "dark")
        self.assertEqual([b["id"] for b in layout["blocks"]], ["hero", "sidebar"])

    @override_settings(**_MANAGER_SETTINGS)
    def test_builder_page_requires_auth(self):
        from django.test import Client

        anon = Client(HTTP_HOST="manager.runmycampus.com", raise_request_exception=False)
        url = reverse("siteconfig:theme_builder")
        resp = anon.get(url)
        self.assertEqual(resp.status_code, 302)

    @override_settings(**_MANAGER_SETTINGS)
    def test_builder_page_200_for_superuser(self):
        url = reverse("siteconfig:theme_builder")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "theme-builder-canvas")
        self.assertContains(resp, "preview-surface-btn")
        self.assertContains(resp, "data-rmc-plane=\"platform\"")

    @override_settings(**_MANAGER_SETTINGS)
    def test_layout_api_round_trip(self):
        url = reverse("siteconfig:theme_builder_layout_api")
        payload = default_layout()
        payload["surface"] = "dark"
        resp = self.client.post(
            url,
            data=json.dumps({"layout": payload}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 200)
        body = get_resp.json()
        self.assertEqual(body["layout"]["surface"], "dark")
        self.assertEqual(body.get("plane"), "operator")
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        stored = (rt.payload or {}).get(OPERATOR_RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(stored.get("surface"), "dark")

    @override_settings(**_MANAGER_SETTINGS)
    def test_preview_api_returns_operator_preview_url(self):
        url = reverse("siteconfig:theme_builder_preview_api")
        resp = self.client.post(
            url,
            data=json.dumps(
                {
                    "colors": {"primary_color": "#112233"},
                    "surface": "dark",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("preview_url", body)
        self.assertEqual(body.get("plane"), "operator")
        self.assertTrue(body["preview_url"].startswith("http"))

    @override_settings(**_MANAGER_SETTINGS)
    def test_publish_api_persists_operator_layout(self):
        url = reverse("siteconfig:theme_builder_publish_api")
        layout = default_layout()
        layout["blocks"] = layout["blocks"][:3]
        resp = self.client.post(
            url,
            data=json.dumps(
                {
                    "layout": layout,
                    "colors": {"primary_color": "#0d6efd"},
                    "publish": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        stored = (rt.payload or {}).get(OPERATOR_RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(len(stored.get("blocks", [])), 3)

    @override_settings(**_MANAGER_SETTINGS)
    def test_builder_page_has_publish_and_preview_controls(self):
        url = reverse("siteconfig:theme_builder")
        resp = self.client.get(url)
        self.assertContains(resp, "theme-builder-publish")
        self.assertContains(resp, "theme-builder-preview")
