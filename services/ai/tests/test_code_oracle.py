"""Code oracle topology reflection."""

from django.test import SimpleTestCase

from services.ai.code_oracle import build_route_manual_outline, inspect_active_route


class CodeOracleTests(SimpleTestCase):
    def test_inspect_admin_login_route(self):
        row = inspect_active_route("/admin/login/")
        self.assertIsNotNone(row)
        self.assertIn("url_path", row)

    def test_manual_outline_has_execution_sections(self):
        outline = build_route_manual_outline("/admin/login/")
        self.assertIn("Execution Path", outline)
        self.assertIn("Action Steps", outline)
