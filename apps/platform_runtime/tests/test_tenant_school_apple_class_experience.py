from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


ROOT = Path(__file__).resolve().parents[3]
SCHOOL_CONFIGURATION_CENTER = (
    ROOT / "templates" / "platform_runtime" / "school_configuration_center.html"
)


class TenantSchoolAppleClassExperienceTests(SimpleTestCase):
    def test_tenant_school_admin_has_next_action_and_drawer(self):
        """MAX operator↔tenant parity wave (6a155f984, 2026-07-21): the bespoke
        apple-class drawer + Option-A strip + operational-center-frame include were
        purged from this page in favour of the shared ``rmc_page_masthead.html``
        chrome + a permission-gated section table (the sibling
        ``test_governed_installation_apple_class_ux`` was updated in the same commit).

        The load-bearing tenant-safe contract survives and is what this asserts:
        the apple-class tenant-school-admin shell scope, the shared masthead, the
        per-section permission gate (so platform-only sections never render), and
        the nav's tenant-scoped guarantee.
        """
        template = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8")
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        bundle = f"{template}\n{nav}"
        # The sweep below runs over template + nav CONCATENATED, so a token found
        # there does not say which file carries it, and all of them survive the
        # template being commented out. Aimed at school_configuration_center.html,
        # the template this case is bound to: the apple-class tenant scope and the
        # per-section marker are markup it must emit, and the shared masthead is
        # an {% include %} it must really pull in. can_access_permission stays a
        # read -- it is the {% if %} gate itself, which no parse can see.
        assert_markup(
            self,
            SCHOOL_CONFIGURATION_CENTER,
            "data-apple-class-tenant-school-admin",
            "data-school-configuration-section",
        )
        assert_wires(
            self, SCHOOL_CONFIGURATION_CENTER, "components/rmc_page_masthead.html"
        )
        for token in (
            # apple-class experience scoped to the tenant school admin
            "data-apple-class-tenant-school-admin",
            # shared masthead chrome (replaced the Option-A strip / center frame here)
            "rmc_page_masthead.html",
            # per-section permission gate → platform-only sections never render
            "can_access_permission",
            "data-school-configuration-section",
            # nav guarantee: tenant-scoped only, no platform-only actions
            "without exposing platform-only actions",
        ):
            with self.subTest(token=token):
                self.assertIn(token, bundle)

    def test_tenant_school_admin_does_not_expose_global_registry(self):
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8").lower()
        self.assertNotIn("global registry", text)
