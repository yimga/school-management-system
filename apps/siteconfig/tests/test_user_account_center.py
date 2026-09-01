from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_does_not_wire,
    assert_renders,
    assert_wires,
    rendered_source,
)

ROOT = Path(__file__).resolve().parents[3]

USER_DROPDOWN = ROOT / "templates/components/user_dropdown.html"
ADMIN_NAV_BRIDGE = ROOT / "templates/components/admin_nav_bridge.html"
ACCOUNT_MENU = ROOT / "templates/components/user_account_center_menu.html"


class UserAccountCenterContractTests(SimpleTestCase):
    def test_canonical_dropdown_mounts_account_center_and_hides_legacy_menu(self):
        assert_wires(self, USER_DROPDOWN, "user_account_center_menu.html")
        # The dropdown renders standalone, so the legacy-menu marker and the
        # runtime script can both be asserted against real OUTPUT -- and the
        # script name is a {% static %} argument that only a render resolves.
        assert_renders(
            self,
            USER_DROPDOWN,
            'data-rmc-account-center-legacy="1"',
            "rmc-user-account-center.js",
        )

    def test_tenant_admin_uses_same_account_component(self):
        source = (ROOT / "templates/components/admin_nav_bridge.html").read_text(encoding="utf-8")
        assert_wires(self, ADMIN_NAV_BRIDGE, "components/user_dropdown.html")
        # The source negative stays: it is STRICTER than assert_does_not_wire,
        # because it also fails if the include is present but commented out.
        self.assertNotIn('include "unfold/helpers/userlinks.html"', source)
        assert_does_not_wire(self, ADMIN_NAV_BRIDGE, "unfold/helpers/userlinks.html")

    def test_account_center_preserves_security_and_both_logout_paths(self):
        source = (ROOT / "templates/components/user_account_center_menu.html").read_text(encoding="utf-8")
        # accounts:mfa_setup is a {% url %} NAME -- a tag argument -- so only a
        # source read can see it.
        self.assertIn("accounts:mfa_setup", source)
        # The logout markers are real output; the menu renders standalone.
        assert_renders(self, ACCOUNT_MENU, 'data-rmc-nav-logout="1"', "forget_device=1")
        # Both "return to" affordances sit behind {% if '/admin/' in request.path %}
        # and then a host branch, so render the menu ONCE PER HOST KIND. That is
        # the behaviour this test names, and a commented-out menu renders neither.
        manager = rendered_source(
            ACCOUNT_MENU,
            {"request": {"path": "/admin/settings/", "public_host_kind": "manager"}},
        )
        tenant = rendered_source(
            ACCOUNT_MENU,
            {"request": {"path": "/admin/settings/", "public_host_kind": "tenant"}},
        )
        self.assertIn("Return to control plane", manager)
        self.assertIn("Return to school portal", tenant)

    def test_runtime_is_local_first_and_privacy_safe(self):
        source = (ROOT / "static/js/rmc-user-account-center.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("offline"', source)
        menu = (ROOT / "templates/components/user_account_center_menu.html").read_text(encoding="utf-8")
        self.assertNotIn("remote_addr", menu)
        self.assertNotIn("last_login", menu)
