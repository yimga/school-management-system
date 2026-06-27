"""No-DB unit coverage for `apps.compliance.validators` (Testing #16, loop 2).

The existing `test_compliance.py` exercises the validators only through
DB-backed ``TestCase`` happy paths. These validators operate entirely on
duck-typed objects / plain data, so the error/warning branches and the two
validators with zero prior coverage (``PrivacyPolicyValidator`` and the
length-bound branch of ``StudentIDValidator``) are pure logic and testable
without a database.

Scope rules: brand-new file, no edits to existing tests or source.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.compliance.validators import (
    CertificateValidator,
    ComplianceValidator,
    PrivacyPolicyValidator,
    RegionalComplianceValidator,
    StudentIDValidator,
)


class ComplianceValidatorBaseTests(SimpleTestCase):
    def test_fresh_validator_is_valid_with_zero_issues(self):
        v = ComplianceValidator(region=None)
        self.assertTrue(v.is_valid())
        self.assertEqual(v.get_issues_count(), 0)

    def test_errors_make_invalid_and_count_includes_warnings(self):
        v = ComplianceValidator(region=None)
        v.add_warning("heads up")
        # A warning alone does not invalidate.
        self.assertTrue(v.is_valid())
        v.add_error("bad")
        self.assertFalse(v.is_valid())
        # count = 1 error + 1 warning.
        self.assertEqual(v.get_issues_count(), 2)

    def test_language_default_is_english(self):
        self.assertEqual(ComplianceValidator(region=None).language, "en")


class StudentIDValidatorTests(SimpleTestCase):
    def _format(self, *, prefix="STU", min_length=5, max_length=10):
        return SimpleNamespace(
            prefix=prefix, min_length=min_length, max_length=max_length
        )

    def test_no_format_passes_open(self):
        # No explicit format and region has no student_id_format -> pass.
        v = StudentIDValidator(region=SimpleNamespace())
        self.assertTrue(v.validate("anything"))
        self.assertEqual(v.get_issues_count(), 0)

    def test_too_short_id_records_error_and_fails(self):
        v = StudentIDValidator(region=SimpleNamespace())
        result = v.validate("ST", self._format())  # length 2 < min 5
        self.assertFalse(result)
        self.assertFalse(v.is_valid())
        self.assertTrue(any("length" in e.lower() for e in v.errors))

    def test_too_long_id_records_error(self):
        v = StudentIDValidator(region=SimpleNamespace())
        result = v.validate("STU12345678901234", self._format())  # > max 10
        self.assertFalse(result)
        self.assertTrue(any("length" in e.lower() for e in v.errors))

    def test_wrong_prefix_is_warning_not_error(self):
        # In-range length but wrong prefix -> warning only, still "valid".
        v = StudentIDValidator(region=SimpleNamespace())
        result = v.validate("XYZ123", self._format())  # length 6 in [5,10]
        self.assertTrue(result)  # warnings don't invalidate
        self.assertEqual(len(v.errors), 0)
        self.assertTrue(any("prefix" in w.lower() for w in v.warnings))

    def test_valid_id_has_no_issues(self):
        v = StudentIDValidator(region=SimpleNamespace())
        self.assertTrue(v.validate("STU123", self._format()))
        self.assertEqual(v.get_issues_count(), 0)

    def test_format_read_from_region_attribute(self):
        region = SimpleNamespace(student_id_format=self._format())
        v = StudentIDValidator(region=region)
        # Wrong length picked up from the region-supplied format.
        self.assertFalse(v.validate("X", id_format=None))
        self.assertTrue(any("length" in e.lower() for e in v.errors))


class CertificateValidatorTests(SimpleTestCase):
    def _complete(self):
        return {
            "student_name": "Ada",
            "course": "Maths",
            "date_issued": "2026-01-01",
            "achievement_level": "A",
        }

    def test_complete_cert_is_valid(self):
        v = CertificateValidator(region=None)
        self.assertTrue(v.validate(self._complete()))
        self.assertEqual(v.get_issues_count(), 0)

    def test_missing_field_records_one_error_per_field(self):
        v = CertificateValidator(region=None)
        data = self._complete()
        del data["course"]
        data["achievement_level"] = ""  # present but empty -> still missing
        self.assertFalse(v.validate(data))
        self.assertEqual(len(v.errors), 2)

    def test_template_requiring_signature_without_it_errors(self):
        v = CertificateValidator(region=None)
        template = SimpleNamespace(requires_principal_signature=True)
        self.assertFalse(v.validate(self._complete(), template=template))
        self.assertTrue(any("signature" in e.lower() for e in v.errors))

    def test_template_signature_present_passes(self):
        v = CertificateValidator(region=None)
        template = SimpleNamespace(requires_principal_signature=True)
        data = self._complete()
        data["principal_signature"] = "Dr. Okoro"
        self.assertTrue(v.validate(data, template=template))


class PrivacyPolicyValidatorTests(SimpleTestCase):
    """Zero prior coverage — pure string analysis."""

    def _full_policy(self):
        # Mention every required section (humanised) plus enough length.
        sections = (
            "data collection, data usage, data protection, user rights, "
            "contact information, effective date."
        )
        padding = "Lorem ipsum compliance copy. " * 30
        return sections + " " + padding

    def test_complete_long_policy_is_valid(self):
        v = PrivacyPolicyValidator(region=None)
        self.assertTrue(v.validate(self._full_policy()))
        self.assertEqual(len(v.errors), 0)

    def test_missing_section_records_error(self):
        v = PrivacyPolicyValidator(region=None)
        text = self._full_policy().replace("user rights", "")
        self.assertFalse(v.validate(text))
        self.assertTrue(any("user_rights" in e for e in v.errors))

    def test_short_policy_adds_warning(self):
        v = PrivacyPolicyValidator(region=None)
        # All sections present but under 500 chars -> warning, no error.
        short = (
            "data collection data usage data protection user rights "
            "contact information effective date"
        )
        result = v.validate(short)
        self.assertTrue(result)  # warning only
        self.assertEqual(len(v.errors), 0)
        self.assertTrue(any("short" in w.lower() for w in v.warnings))

    def test_case_insensitive_section_matching(self):
        v = PrivacyPolicyValidator(region=None)
        upper = self._full_policy().upper()
        self.assertTrue(v.validate(upper))
        self.assertEqual(len(v.errors), 0)


class RegionalComplianceValidatorTests(SimpleTestCase):
    def test_no_requirements_warns_and_passes(self):
        v = RegionalComplianceValidator(region=None)
        self.assertTrue(v.validate_region_compliance([]))
        self.assertTrue(any("no requirements" in w.lower() for w in v.warnings))

    def test_overdue_requirement_errors(self):
        v = RegionalComplianceValidator(region=None)
        reqs = [
            SimpleNamespace(status="pending", is_overdue=lambda: True),
            SimpleNamespace(status="active", is_overdue=lambda: False),
        ]
        self.assertFalse(v.validate_region_compliance(reqs))
        self.assertTrue(any("overdue" in e.lower() for e in v.errors))

    def test_compliance_score_empty_is_zero(self):
        v = RegionalComplianceValidator(region=None)
        self.assertEqual(v.generate_compliance_score([]), 0)

    def test_compliance_score_rounds_to_one_decimal(self):
        v = RegionalComplianceValidator(region=None)
        reqs = [
            SimpleNamespace(status="implemented"),
            SimpleNamespace(status="active"),
            SimpleNamespace(status="pending"),
        ]
        # 2 of 3 completed -> 66.7
        self.assertEqual(v.generate_compliance_score(reqs), 66.7)

    def test_compliance_score_all_complete_is_hundred(self):
        v = RegionalComplianceValidator(region=None)
        reqs = [SimpleNamespace(status="active"), SimpleNamespace(status="implemented")]
        self.assertEqual(v.generate_compliance_score(reqs), 100.0)
