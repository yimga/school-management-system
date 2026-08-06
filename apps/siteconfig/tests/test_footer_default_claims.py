"""Tenant footer default-content honesty contract.

Regression guards for the audit findings on ``templates/components/dashboard_footer.html``:

* the default trust pill asserted specific, audited certifications (FERPA / ISO
  27001 / WCAG 2.1 AA) on EVERY school's own portal — a misleading legal claim;
* the brand descriptor defaulted to "Family portal", wrong for admins/teachers;
* the contacts block leaked the PLATFORM's phone/email onto tenant footers.
"""

from pathlib import Path

from django.test import SimpleTestCase

FOOTER = Path("templates/components/dashboard_footer.html")


class FooterDefaultClaimsTests(SimpleTestCase):
    def setUp(self):
        self.src = FOOTER.read_text(encoding="utf-8")

    def test_no_default_certification_claims_rendered(self):
        # The rendered pill literal (middot-joined) must be gone. A slash-joined
        # mention inside the explanatory {% comment %} is allowed (not rendered).
        self.assertNotIn("FERPA · ISO 27001 · WCAG 2.1 AA", self.src)
        self.assertIn("Secure &amp; private", self.src)

    def test_descriptor_default_is_role_neutral(self):
        self.assertNotIn('descriptor|default:"Family portal"', self.src)
        self.assertIn('descriptor|default:"School portal"', self.src)

    def test_platform_contacts_are_gated_to_manager_host(self):
        # The SITE.company_* fallback (platform contacts) must sit inside a
        # manager-host guard so a tenant footer never shows RunMyCampus's contacts.
        self.assertIn("request.public_host_kind == 'manager'", self.src)
        guard_idx = self.src.index("request.public_host_kind == 'manager'")
        phone_idx = self.src.index("SITE.company_phone")
        email_idx = self.src.index("SITE.company_email")
        self.assertLess(guard_idx, phone_idx)
        self.assertLess(guard_idx, email_idx)
