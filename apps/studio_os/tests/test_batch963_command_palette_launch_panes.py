"""PATH III.33: command palette includes Launch Studio deep links (migration, role preview)."""

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.studio_os.services import get_studio_command_palette_entries


class CommandPaletteLaunchPaneTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = SimpleNamespace(pk=1)

    def test_migration_and_role_preview_entries(self):
        req = self.rf.get("/studio/launch/")
        req.user = SimpleNamespace()
        req.school = self.school
        entries = get_studio_command_palette_entries(req)
        labels = [e.get("label", "") for e in entries]
        joined = " ".join(labels).lower()
        self.assertIn("migration", joined)
        self.assertIn("preview", joined)
        urls = [e.get("url", "") for e in entries if "migration" in e.get("label", "").lower()]
        self.assertTrue(any("pane=migration" in u for u in urls))
        rp = [e.get("url", "") for e in entries if "preview by role" in e.get("label", "").lower()]
        self.assertTrue(any("pane=role_preview" in u for u in rp))
