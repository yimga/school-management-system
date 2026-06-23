"""Wave 5 — compliance regime auto-derived from country at signup.

School.compliance_region (GDPR/FERPA/NDPR) gated masking/retention/consent but signup
never set it, so every new tenant defaulted to NONE. derive_compliance_region maps a
country to the regime we implement; signup now persists it.
"""

from django.test import SimpleTestCase


class DeriveComplianceRegionTests(SimpleTestCase):
    def test_eu_eea_uk_map_to_gdpr(self):
        from apps.schools.compliance_region import derive_compliance_region

        for cc in ("FR", "DE", "IE", "NO", "GB", "es"):  # incl. lowercase + EEA + UK
            self.assertEqual(derive_compliance_region(cc), "EU", cc)

    def test_us_maps_to_ferpa(self):
        from apps.schools.compliance_region import derive_compliance_region

        self.assertEqual(derive_compliance_region("US"), "US")

    def test_nigeria_maps_to_ndpr(self):
        from apps.schools.compliance_region import derive_compliance_region

        self.assertEqual(derive_compliance_region("NG"), "NDPR")

    def test_unmapped_country_is_unset(self):
        from apps.schools.compliance_region import derive_compliance_region

        self.assertEqual(derive_compliance_region("CM"), "")
        self.assertEqual(derive_compliance_region(""), "")
        self.assertEqual(derive_compliance_region(None), "")

    def test_returned_values_are_valid_compliance_region_choices(self):
        from apps.schools.compliance_region import derive_compliance_region
        from apps.schools.models import School

        valid = {c.value for c in School.ComplianceRegion}
        for cc in ("FR", "US", "NG", "CM", "", None):
            self.assertIn(derive_compliance_region(cc), valid)

    def test_signup_view_assigns_compliance_region(self):
        # Contract: the signup create path wires the derivation into create_kwargs.
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "signup_views.py"
        ).read_text(encoding="utf-8")
        self.assertIn("derive_compliance_region(country_code)", src)
        self.assertIn("compliance_region=derive_compliance_region", src)
