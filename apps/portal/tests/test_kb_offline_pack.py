"""Tests for KB offline pack API (batch 1650)."""

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory
from apps.portal.views_kb_offline import api_kb_offline_pack

User = get_user_model()


class KbOfflinePackTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="kb_offline_staff",
            password="Test1234",
            role=User.Role.ADMIN,
        )
        cat = KBCategory.objects.create(name="Ops", slug="ops")
        self.article = KBArticle.objects.create(
            title="Offline help article",
            slug="offline-help-article",
            summary="Summary",
            content="Body for offline read.",
            category=cat,
            help_audience=HelpAudience.TENANT,
            status="PUBLISHED",
            locale="en",
        )

    def test_offline_pack_returns_published_article(self):
        request = self.factory.get("/portal/api/v1/kb/offline-pack/")
        request.user = self.user
        request.public_host_kind = "tenant"
        request.school = None
        response = api_kb_offline_pack(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertGreaterEqual(payload.get("count", 0), 1)
        slugs = {row["slug"] for row in payload.get("results", [])}
        self.assertIn("offline-help-article", slugs)

    def test_offline_pack_route_resolves(self):
        url = reverse("portal:kb_offline_pack")
        self.assertIn("offline-pack", url)
