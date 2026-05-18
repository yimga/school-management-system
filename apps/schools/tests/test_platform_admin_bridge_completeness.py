"""
Every model registered on ``platform_admin_site`` must have a matching
``super:admin_bridge`` entry (``PLATFORM_ADMIN_BRIDGES`` admin_url).
"""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from config.admin import platform_admin_site

from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES


def _admin_changelist_path_tail(admin_url_name: str) -> str:
    loc = reverse(str(admin_url_name)).lower()
    parts = [p for p in loc.split("/") if p]
    return parts[-1] if parts else ""


def _changelist_name(model):
    opts = model._meta
    return f"admin:{opts.app_label}_{opts.model_name}_changelist"


@override_settings(ALLOWED_HOSTS=["*"])
class PlatformAdminBridgeCompletenessTests(TestCase):
    def test_every_platform_admin_model_has_admin_bridge(self):
        platform_urls = {_changelist_name(m) for m in platform_admin_site._registry.keys()}
        bridge_urls = {str(v["admin_url"]) for v in PLATFORM_ADMIN_BRIDGES.values()}
        missing = sorted(platform_urls - bridge_urls)
        self.assertEqual(
            missing,
            [],
            f"platform_admin_site changelists missing from PLATFORM_ADMIN_BRIDGES: {missing}",
        )

    def test_sample_new_surface_bridge_redirects(self):
        """Smoke: extended surface bridges 302 to expected admin path (manager host)."""
        user = User.objects.create_user(
            username="bridge_complete",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        cache.clear()
        for key in (
            "marketplace_marketplaceapp",
            "billing_billingaccount",
            "schools_school",
            "registries_countryregistry",
        ):
            with self.subTest(key=key):
                url = reverse("super:admin_bridge", kwargs={"bridge_key": key})
                r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
                self.assertEqual(r.status_code, 302, key)
                admin_url = PLATFORM_ADMIN_BRIDGES[key]["admin_url"]
                needle = _admin_changelist_path_tail(str(admin_url))
                self.assertIn(needle, r.get("Location", "").lower(), msg=key)

    def test_show_in_nav_bridge_keys_redirect(self):
        """Every show_in_nav registry entry must 302 via super:admin_bridge."""
        user = User.objects.create_user(
            username="bridge_show_in_nav",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        cache.clear()
        for key in PLATFORM_ADMIN_BRIDGE_ORDER:
            meta = PLATFORM_ADMIN_BRIDGES.get(key)
            if not meta or not meta.get("show_in_nav"):
                continue
            with self.subTest(key=key):
                url = reverse("super:admin_bridge", kwargs={"bridge_key": key})
                r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
                self.assertEqual(r.status_code, 302, key)
                admin_url = meta["admin_url"]
                needle = _admin_changelist_path_tail(str(admin_url))
                self.assertIn(needle, r.get("Location", "").lower(), msg=key)
