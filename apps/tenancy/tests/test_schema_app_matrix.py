from django.test import SimpleTestCase

from apps.tenancy.checks import SCHEMA_REQUIRED_APPS
from config import settings as project_settings


class SchemaAppMatrixTests(SimpleTestCase):
    def test_schema_required_apps_are_present_in_shared_apps(self):
        settings_text = project_settings.BASE_DIR.joinpath("config", "settings.py").read_text(encoding="utf-8")
        missing = sorted(app for app in SCHEMA_REQUIRED_APPS if app not in settings_text)
        self.assertEqual(missing, [], msg=f"Missing schema shared apps: {missing}")
