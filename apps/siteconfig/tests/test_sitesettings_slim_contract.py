from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.siteconfig import models as _siteconfig_models
from apps.siteconfig.sitesettings_slim_contract import (
    SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES,
    assert_sitesettings_slim_contract,
    sitesettings_slim_db_errors,
    sitesettings_slim_model_errors,
)

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")


class SiteSettingsSlimContractTests(SimpleTestCase):
    def test_model_matches_slim_contract(self) -> None:
        assert_sitesettings_slim_contract()

    def test_expected_field_set_documented(self) -> None:
        self.assertEqual(sitesettings_slim_model_errors(), [])
        names = {f.name for f in _TenantSettingsModel._meta.local_concrete_fields}
        self.assertEqual(names, SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)


class SiteSettingsSlimDbContractTests(TestCase):
    def test_physical_table_columns_match_slim_contract(self) -> None:
        errs = sitesettings_slim_db_errors(connection)
        self.assertEqual(errs, [], msg=errs[0] if errs else "")


class SiteSettingsSlimDbTableGuardTests(SimpleTestCase):
    def test_db_errors_rejects_malformed_db_table_without_introspection(self) -> None:
        fake_model = SimpleNamespace(_meta=SimpleNamespace(db_table="x;y"))
        with (
            patch(
                "apps.siteconfig.sitesettings_slim_contract._tenant_settings_model",
                return_value=fake_model,
            ),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            errs = sitesettings_slim_db_errors(connection)

        table_names.assert_not_called()
        self.assertEqual(len(errs), 1)
        self.assertIn("slim DB check", errs[0])
        self.assertIn("not a safe Django table identifier", errs[0])

    def test_db_errors_rejects_blank_db_table_without_introspection(self) -> None:
        fake_model = SimpleNamespace(_meta=SimpleNamespace(db_table="   "))
        with (
            patch(
                "apps.siteconfig.sitesettings_slim_contract._tenant_settings_model",
                return_value=fake_model,
            ),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            errs = sitesettings_slim_db_errors(connection)

        table_names.assert_not_called()
        self.assertEqual(len(errs), 1)
        self.assertIn("blank", errs[0].lower())
