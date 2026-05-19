"""Theme builder canvas + layout API."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.theme_builder import RUNTIME_PAYLOAD_KEY, default_layout, normalize_layout


class ThemeBuilderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username=f"builder_{uuid.uuid4().hex[:8]}",
            password="Test1234",
            email="builder@example.com",
        )
        self.client = Client()
        self.client.force_login(self.user)

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

    def test_builder_page_requires_auth(self):
        anon = Client()
        url = reverse("siteconfig:theme_builder")
        resp = anon.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_builder_page_200_for_superuser(self):
        url = reverse("siteconfig:theme_builder")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "theme-builder-canvas")
        self.assertContains(resp, "preview-surface-btn")

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
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        stored = (rt.payload or {}).get(RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(stored.get("surface"), "dark")

    def test_preview_api_sets_session_overlay(self):
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
        from apps.siteconfig.context_processors import SESSION_KEY

        overlay = self.client.session.get(SESSION_KEY) or {}
        self.assertTrue(overlay.get("use_dark_mode"))

    def test_publish_api_persists_layout(self):
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
        stored = (rt.payload or {}).get(RUNTIME_PAYLOAD_KEY) or {}
        self.assertEqual(len(stored.get("blocks", [])), 3)

    def test_builder_page_has_publish_and_preview_controls(self):
        url = reverse("siteconfig:theme_builder")
        resp = self.client.get(url)
        self.assertContains(resp, "theme-builder-publish")
        self.assertContains(resp, "theme-builder-preview")
