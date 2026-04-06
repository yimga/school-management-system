"""
Catalog/admission config audit: test that admission number generation and validation
use centralized config (tenant site-settings row or TenantAdmissionNumberPolicy) and assert format.
"""

from django.test import TestCase

from apps.siteconfig.identifier_policy_service import (
    get_admissions_policy,
    preview_admission_number,
    validate_admission_number,
)
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.tests.payload_helpers import persist_runtime_site_settings_payload


class AdmissionConfigTestCase(TestCase):
    """Test admission number config resolution and format."""

    def setUp(self):
        get_platform_site_settings_record(create=True)
        persist_runtime_site_settings_payload(
            school_code="GIL",
            admission_number_strategy="FULL",
            admission_number_template="",
            admission_number_pattern=(
                r"^\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{0,4}$"
            ),
        )

    def test_preview_uses_policy(self):
        """Preview returns format from policy when school is None (platform tenant site-settings row)."""
        out = preview_admission_number(
            None,
            year_2digit="26",
            school_code="GIL",
            seq_4digit="0001",
            spec_code="GEN",
            class_segment="F1",
        )
        self.assertEqual(out, "26GIL0001GENF1")

    def test_preview_year_seq_strategy(self):
        """Preview respects YEAR_SEQ strategy when set."""
        get_platform_site_settings_record(create=True)
        persist_runtime_site_settings_payload(
            school_code="GIL",
            admission_number_strategy="YEAR_SEQ",
        )
        out = preview_admission_number(
            None, year_2digit="26", school_code="GIL", seq_4digit="0001"
        )
        self.assertEqual(out, "26GIL0001")

    def test_validate_matches_pattern(self):
        """Validation returns True for value matching policy pattern."""
        self.assertTrue(validate_admission_number(None, "26GIL0001GENF1"))
        self.assertFalse(validate_admission_number(None, "invalid"))

    def test_policy_resolution_site_defaults(self):
        """get_admissions_policy(None) returns platform tenant site-settings-based config."""
        policy = get_admissions_policy(None)
        self.assertIn("school_code", policy)
        self.assertIn("admission_number_strategy", policy)
        self.assertIn("admission_number_template", policy)
        self.assertIn("admission_number_pattern", policy)
        self.assertEqual(policy.get("school_code"), "GIL")
