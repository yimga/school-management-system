"""Configure hub — one category per slug, static settings chrome."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_every_entry_resolves_on_tenant_host(self):
        """Every configure tile must reverse on the TENANT urlconf it renders under.

        ``_build_catalog`` resolves each entry's URL via ``_try_url`` at build
        time using the request's urlconf; a name that does not resolve there
        yields ``url=None`` and the tile is SILENTLY dropped (the exact failure
        of the earlier ``tenant_import_setup`` typo). This must-fire guard walks
        every entry and fails on any dropped tile — so a mis-wired route can
        never quietly vanish again.
        """
        dropped = [
            (cat.label, entry.label)
            for cat in _build_catalog()
            for entry in cat.entries
            if entry.url is None
        ]
        self.assertEqual(dropped, [], f"configure tiles dropped on tenant host: {dropped}")

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
