"""Unit tests for siteconfig.geoip_service (no ORM; cache + static defaults)."""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.siteconfig.geoip_service import (
    GeoIPEventLogger,
    GeoIPService,
    LocationBasedAccessControl,
    REGION_DEFAULTS,
    RegionalConfigSnapshot,
    RegionalDataLocalization,
)


class GeoIPServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_lookup_ip_cache_roundtrip(self):
        payload = {
            "ip": "203.0.113.10",
            "country_code": "NG",
            "country_name": "Nigeria",
            "city": "Lagos",
            "latitude": 6.45,
            "longitude": 3.39,
            "timezone": "Africa/Lagos",
            "isp": "",
            "is_vpn": False,
            "is_proxy": False,
        }
        cache.set("geoip:203.0.113.10", payload, 60)
        self.assertEqual(GeoIPService.lookup_ip("203.0.113.10"), payload)

    def test_lookup_ip_miss_returns_none(self):
        self.assertIsNone(GeoIPService.lookup_ip("198.51.100.1"))

    def test_get_user_region_maps_country(self):
        cache.set(
            "geoip:203.0.113.20",
            {"country_code": "KE", "country_name": "Kenya"},
            60,
        )
        self.assertEqual(GeoIPService.get_user_region("203.0.113.20"), "EAST_AFRICA")

    def test_get_region_config_static(self):
        cfg = GeoIPService.get_region_config("WEST_AFRICA")
        self.assertIsInstance(cfg, RegionalConfigSnapshot)
        self.assertEqual(cfg.currency, "NGN")

    def test_calculate_distance(self):
        # ~600 km order of magnitude Lagos — Abuja (rough sanity)
        d = GeoIPService.calculate_distance(6.45, 3.39, 9.08, 7.53)
        self.assertGreater(d, 400)
        self.assertLess(d, 900)

    def test_is_ip_whitelisted_false(self):
        self.assertFalse(GeoIPService.is_ip_whitelisted("10.0.0.1"))

    def test_check_region_access_false(self):
        self.assertFalse(GeoIPService.check_region_access("WEST_AFRICA", "staff"))


class RegionalDataLocalizationTests(SimpleTestCase):
    def test_get_regional_currency_west_africa(self):
        self.assertEqual(
            RegionalDataLocalization.get_regional_currency("WEST_AFRICA"), "NGN"
        )

    def test_get_regional_languages(self):
        langs = RegionalDataLocalization.get_regional_languages("WEST_AFRICA")
        self.assertIn("en", langs)

    def test_format_currency_uses_symbol(self):
        s = RegionalDataLocalization.format_currency(1000.5, "WEST_AFRICA")
        self.assertIn("1,000.50", s)

    def test_apply_regional_rules_with_cached_geo(self):
        cache.set(
            "geoip:203.0.113.30",
            {"country_code": "NG"},
            60,
        )
        rules = RegionalDataLocalization.apply_regional_rules(1, "203.0.113.30")
        self.assertEqual(rules["region"], "WEST_AFRICA")
        self.assertEqual(rules["currency"], "NGN")


class LocationBasedAccessControlTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_denied_without_geo(self):
        ctrl = LocationBasedAccessControl("198.51.100.2")
        self.assertFalse(ctrl.is_allowed())
        self.assertEqual(ctrl.get_access_level(), "denied")

    def test_allowed_with_geo_no_vpn(self):
        cache.set(
            "geoip:203.0.113.40",
            {
                "country_code": "NG",
                "is_vpn": False,
                "is_proxy": False,
            },
            60,
        )
        ctrl = LocationBasedAccessControl("203.0.113.40")
        self.assertTrue(ctrl.is_allowed())
        self.assertEqual(ctrl.get_access_level(), "full")


class GeoIPEventLoggerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_log_access_writes_cache(self):
        cache.set(
            "geoip:203.0.113.50",
            {"country_code": "GH", "city": "Accra"},
            60,
        )
        GeoIPEventLogger.log_access("203.0.113.50", 99, "/x/", True)
        ev = cache.get("geo_event:203.0.113.50:99:/x/")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["country"], "GH")


class RegionDefaultsTests(SimpleTestCase):
    def test_all_macro_regions_have_defaults(self):
        for key in RegionalDataLocalization.REGIONAL_LANGUAGES:
            self.assertIn(key, REGION_DEFAULTS, msg=f"missing REGION_DEFAULTS[{key}]")
