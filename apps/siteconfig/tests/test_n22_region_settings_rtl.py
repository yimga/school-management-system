"""N22: region_settings exposes is_rtl for portal_base dir=rtl."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings

from apps.siteconfig.context_processors import region_settings
from apps.siteconfig.models import RegionConfig


class RegionSettingsRtlTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(REGION_CODE="TSTRTL")
    def test_is_rtl_true_when_region_configured_rtl(self):
        RegionConfig.objects.update_or_create(
            code="TSTRTL",
            defaults={
                "name": "Test RTL",
                "default_currency": "USD",
                "timezone": "UTC",
                "default_language": "en",
                "is_rtl": True,
            },
        )
        request = self.factory.get("/portal/")
        request.user = AnonymousUser()
        request.session = {"region_code": "TSTRTL"}
        ctx = region_settings(request)
        self.assertTrue(ctx.get("is_rtl"))

    @override_settings(REGION_CODE="TSTLTR")
    def test_is_rtl_false_when_region_not_rtl(self):
        RegionConfig.objects.update_or_create(
            code="TSTLTR",
            defaults={
                "name": "Test LTR",
                "default_currency": "USD",
                "timezone": "UTC",
                "default_language": "en",
                "is_rtl": False,
            },
        )
        request = self.factory.get("/portal/")
        request.user = AnonymousUser()
        request.session = {"region_code": "TSTLTR"}
        ctx = region_settings(request)
        self.assertFalse(ctx.get("is_rtl"))
