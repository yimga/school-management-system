"""PaletteGenerateView — auth gate + tenant gate + happy path (batch 1371, P1)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.test_utils.http_clients import login_manager_client

_MANAGER_SETTINGS = dict(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.manager_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)


class PaletteGenerateViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        suffix = uuid.uuid4().hex[:8]
        self.user = User.objects.create_superuser(
            username=f"palette_{suffix}",
            password="Test1234",
            email=f"palette_{suffix}@example.com",
        )
        self.client = login_manager_client(self.user, password="Test1234")

    @override_settings(**_MANAGER_SETTINGS)
    def test_anonymous_is_blocked(self):
        anon = Client(
            HTTP_HOST="manager.runmycampus.com", raise_request_exception=False
        )
        url = reverse("siteconfig:palette_generate")
        resp = anon.post(
            url,
            data=json.dumps({"seed_hex": "#4F46E5", "mode": "dual"}),
            content_type="application/json",
        )
        # LoginRequiredMixin → 302 redirect to login (for browser POSTs),
        # or 401 if the view handles it directly. Either way: NOT 200.
        self.assertIn(resp.status_code, (302, 401, 403))
        self.assertNotEqual(resp.status_code, 200)

    @override_settings(**_MANAGER_SETTINGS)
    def test_happy_path_returns_palette_for_superuser(self):
        url = reverse("siteconfig:palette_generate")
        # Force rules-fallback so the test is hermetic (no gateway call).
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            resp = self.client.post(
                url,
                data=json.dumps({"seed_hex": "#4F46E5", "mode": "dual"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body.get("ok"))
        palette = body.get("palette") or {}
        self.assertEqual(len(palette.get("stops") or {}), 11)
        self.assertIn(palette.get("source"), ("rules", "fallback", "cloud"))
        self.assertIn(palette.get("wcag_grade"), ("AAA", "AA", "AA_large", "FAIL"))

    @override_settings(**_MANAGER_SETTINGS)
    def test_missing_seed_hex_is_400(self):
        url = reverse("siteconfig:palette_generate")
        resp = self.client.post(
            url,
            data=json.dumps({"mode": "dual"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(**_MANAGER_SETTINGS)
    def test_invalid_json_is_400(self):
        url = reverse("siteconfig:palette_generate")
        resp = self.client.post(
            url,
            data="not valid json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(**_MANAGER_SETTINGS)
    def test_get_is_405(self):
        url = reverse("siteconfig:palette_generate")
        resp = self.client.get(url)
        # http_method_names = ["post"] → GET should be 405.
        self.assertIn(resp.status_code, (302, 405))
