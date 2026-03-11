import sys
from types import ModuleType
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts import security_audit


class SecurityAuditHelperTests(SimpleTestCase):
    def test_get_location_data_returns_empty_for_blank_ip(self):
        self.assertEqual(security_audit._get_location_data(""), {})

    def test_get_location_data_returns_empty_when_geoip_reader_fails(self):
        geoip2_module = ModuleType("geoip2")
        geoip2_database = ModuleType("geoip2.database")
        geoip2_errors = ModuleType("geoip2.errors")

        class FakeGeoIP2Error(Exception):
            pass

        class FakeReader:
            def __init__(self, _path):
                raise FakeGeoIP2Error("boom")

        geoip2_database.Reader = FakeReader
        geoip2_errors.GeoIP2Error = FakeGeoIP2Error
        geoip2_module.database = geoip2_database
        geoip2_module.errors = geoip2_errors

        fake_modules = {
            "geoip2": geoip2_module,
            "geoip2.database": geoip2_database,
            "geoip2.errors": geoip2_errors,
        }

        with patch.dict(sys.modules, fake_modules, clear=False):
            with patch("os.path.isfile", return_value=True):
                self.assertEqual(security_audit._get_location_data("1.1.1.1"), {})
