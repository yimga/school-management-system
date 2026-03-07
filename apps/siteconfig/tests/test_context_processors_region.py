"""
Tests for region_settings and language_context when user has preferred_region / preferred_language.
"""
from unittest.mock import MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from apps.siteconfig.models import RegionConfig, UserPreference
from apps.siteconfig.context_processors import region_settings, language_context

User = get_user_model()


class RegionSettingsPreferredRegionTests(TestCase):
    def setUp(self):
        RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "date_format": "DD/MM/YYYY",
                "default_currency": "XAF",
                "decimal_separator": ".",
                "thousands_separator": ",",
            },
        )
        RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "date_format": "MM/DD/YYYY",
                "default_currency": "USD",
                "decimal_separator": ".",
                "thousands_separator": ",",
            },
        )

    def test_anonymous_uses_session_or_default(self):
        request = MagicMock()
        request.user.is_authenticated = False
        request.session = {"region_code": "USA"}
        ctx = region_settings(request)
        self.assertEqual(ctx["region_code"], "USA")

    def test_authenticated_with_preferred_region_uses_it(self):
        user = User.objects.create_user(username="t1", password="test")
        UserPreference.objects.create(user=user, preferred_region="USA")
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.preferences = user.preferences
        request.session = {"region_code": "CMR"}
        ctx = region_settings(request)
        self.assertEqual(ctx["region_code"], "USA")

    def test_authenticated_without_preferred_region_uses_session(self):
        user = User.objects.create_user(username="t2", password="test")
        UserPreference.objects.create(user=user, preferred_region="")
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.preferences = user.preferences
        request.session = {"region_code": "USA"}
        ctx = region_settings(request)
        self.assertEqual(ctx["region_code"], "USA")

    def test_context_contains_enable_multi_region(self):
        request = MagicMock()
        request.user.is_authenticated = False
        request.session = {}
        ctx = region_settings(request)
        self.assertIn("enable_multi_region", ctx)


class LanguageContextPreferredLanguageTests(TestCase):
    def setUp(self):
        RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={"name": "Cameroon", "default_language": "en"},
        )

    def test_authenticated_with_preferred_language_uses_it(self):
        user = User.objects.create_user(username="lang1", password="test")
        UserPreference.objects.create(user=user, preferred_language="fr")
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.preferences = user.preferences
        request.GET = {}
        request.COOKIES = {}
        ctx = language_context(request)
        self.assertEqual(ctx["current_language"], "fr")
        self.assertEqual(ctx["current_language_name"], "Français")
