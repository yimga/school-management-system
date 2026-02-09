import tempfile
from pathlib import Path
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.siteconfig.management.commands.import_ui_config import Command as ImportUIConfigCommand
from apps.siteconfig.models import SiteSettings, ThemePack


class UIConfigCommandTests(TestCase):
    def setUp(self):
        SiteSettings.objects.all().delete()
        ThemePack.objects.all().delete()
        self.theme = ThemePack.objects.create(
            name="Base Theme",
            slug="base-theme",
            is_default=True,
            applies_to_admin=True,
            is_active=True,
        )
        SiteSettings.objects.create(theme_pack=self.theme)

    def test_export_ui_config_writes_non_empty_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ui_export.json"
            call_command("export_ui_config", "--output", str(output))
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 2)
            text = output.read_text(encoding="utf-8")
            self.assertIn("siteconfig.sitesettings", text)
            self.assertIn("siteconfig.themepack", text)

    def test_import_ui_config_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text("", encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("import_ui_config", str(empty))

    def test_import_command_creates_missing_compliance_profile_dependency(self):
        ComplianceProfile.objects.all().delete()
        cmd = ImportUIConfigCommand()
        cmd._ensure_dependencies(
            [{"model": "siteconfig.sitesettings", "fields": {"compliance_profile": 321}}]
        )
        self.assertTrue(ComplianceProfile.objects.filter(pk=321).exists())

    def test_check_ui_parity_passes_for_fresh_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ui_export.json"
            call_command("export_ui_config", "--output", str(output))
            stdout = StringIO()
            call_command("check_ui_parity", "--input-file", str(output), "--strict", stdout=stdout)
            self.assertIn("UI parity check passed", stdout.getvalue())

    def test_check_ui_parity_strict_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ui_export.json"
            call_command("export_ui_config", "--output", str(output))
            site = SiteSettings.objects.order_by("pk").first()
            site.primary_color = "#ffffff"
            site.save(update_fields=["primary_color"])
            with self.assertRaises(CommandError):
                call_command("check_ui_parity", "--input-file", str(output), "--strict")
