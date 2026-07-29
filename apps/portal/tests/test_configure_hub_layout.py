"""Configure hub — one category per slug, static settings chrome."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.portal.views_configure import _build_catalog


class ConfigureHubLayoutTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="configure-hub-admin",
            password="Test1234!",
            is_staff=True,
        )

    def test_catalog_has_unique_slugs(self):
        slugs = [c.slug for c in _build_catalog()]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_render_one_section_per_category(self):
        self.client.force_login(self.user)
        url = reverse("portal_configure")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-page-archetype="settings-hub"', html)
        self.assertIn('data-rmc-static-chrome="1"', html)
        self.assertNotIn("rmc-settings-section rmc-reveal", html)
        for cat in _build_catalog():
            self.assertEqual(html.count(f'id="cat-{cat.slug}"'), 1)
        self.assertNotIn("rmc-flow-launchpad", html)
