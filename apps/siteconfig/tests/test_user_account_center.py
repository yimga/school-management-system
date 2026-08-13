from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class UserAccountCenterContractTests(SimpleTestCase):
    def test_canonical_dropdown_mounts_account_center_and_hides_legacy_menu(self):
        source = (ROOT / "templates/components/user_dropdown.html").read_text(encoding="utf-8")
        self.assertIn("user_account_center_menu.html", source)
        self.assertIn('data-rmc-account-center-legacy="1"', source)
        self.assertIn("rmc-user-account-center.js", source)

    def test_tenant_admin_uses_same_account_component(self):
        source = (ROOT / "templates/components/admin_nav_bridge.html").read_text(encoding="utf-8")
        self.assertIn('include "components/user_dropdown.html"', source)
        self.assertNotIn('include "unfold/helpers/userlinks.html"', source)

    def test_account_center_preserves_security_and_both_logout_paths(self):
        source = (ROOT / "templates/components/user_account_center_menu.html").read_text(encoding="utf-8")
        self.assertIn("accounts:mfa_setup", source)
        self.assertIn('data-rmc-nav-logout="1"', source)
        self.assertIn("forget_device=1", source)
        self.assertIn("Return to control plane", source)
        self.assertIn("Return to school portal", source)

    def test_runtime_is_local_first_and_privacy_safe(self):
        source = (ROOT / "static/js/rmc-user-account-center.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("offline"', source)
        menu = (ROOT / "templates/components/user_account_center_menu.html").read_text(encoding="utf-8")
        self.assertNotIn("remote_addr", menu)
        self.assertNotIn("last_login", menu)
