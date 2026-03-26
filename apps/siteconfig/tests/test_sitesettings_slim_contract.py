from __future__ import annotations

from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.siteconfig.sitesettings_slim_contract import (
    SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES,
    assert_sitesettings_slim_contract,
    sitesettings_slim_db_errors,
    sitesettings_slim_model_errors,
)


class SiteSettingsSlimContractTests(SimpleTestCase):
    def test_model_matches_slim_contract(self) -> None:
        assert_sitesettings_slim_contract()

    def test_expected_field_set_documented(self) -> None:
        self.assertEqual(sitesettings_slim_model_errors(), [])
        from apps.siteconfig.models import SiteSettings

        names = {f.name for f in SiteSettings._meta.local_concrete_fields}
        self.assertEqual(names, SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)


class SiteSettingsSlimDbContractTests(TestCase):
    def test_physical_table_columns_match_slim_contract(self) -> None:
        errs = sitesettings_slim_db_errors(connection)
        self.assertEqual(errs, [], msg=errs[0] if errs else "")
