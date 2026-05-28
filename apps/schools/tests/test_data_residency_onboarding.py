"""Tests for data_residency_onboarding (batch 1530)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.schools.data_residency_onboarding import apply_data_residency_for_new_school


class DataResidencyOnboardingTests(SimpleTestCase):
    @patch(
        "apps.schools.data_residency_onboarding.derive_default_region",
        return_value="eu_central",
    )
    def test_apply_sets_region_from_country(self, _mock_derive):
        school = SimpleNamespace(
            country_code="DE",
            data_region="",
            settings={},
            pk=1,
            slug="test-school",
        )
        out = apply_data_residency_for_new_school(school, source="test")
        self.assertEqual(school.data_region, "eu_central")
        self.assertEqual(out["data_region"], "eu_central")
        self.assertIn("data_residency", school.settings)


class DataResidencyFailureAuditTests(TestCase):
    """v4.00.3 audit lock: signup_views must not silently swallow
    data-residency assignment failures. Prior to this wave, a bare
    ``except Exception: pass`` masked the call, leaving GDPR / data-region
    obligations unmet without log, event, or operator signal."""

    def test_failure_records_provisioning_event_and_returns_false(self):
        from apps.schools.models import School, SchoolProvisioningEvent
        from apps.schools.signup_views import (
            _assign_data_residency_or_record_failure,
        )

        school = School.objects.create(
            name="Residency Fail",
            slug="residency-fail-school",
            subdomain="residency-fail-school",
            is_active=False,
        )
        with patch(
            "apps.schools.data_residency_onboarding.apply_data_residency_for_new_school",
            side_effect=ValueError("region lookup table missing"),
        ):
            ok = _assign_data_residency_or_record_failure(school)
        self.assertFalse(ok)
        event = SchoolProvisioningEvent.objects.filter(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.FAILED,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.status, SchoolProvisioningEvent.Status.WARNING)
        self.assertEqual(event.payload.get("phase"), "data_residency")
        self.assertEqual(event.payload.get("error_type"), "ValueError")
        self.assertIn("region lookup table missing", event.payload.get("error", ""))

    def test_success_does_not_record_event(self):
        from apps.schools.models import School, SchoolProvisioningEvent
        from apps.schools.signup_views import (
            _assign_data_residency_or_record_failure,
        )

        school = School.objects.create(
            name="Residency OK",
            slug="residency-ok-school",
            subdomain="residency-ok-school",
            country_code="US",
            is_active=False,
        )
        ok = _assign_data_residency_or_record_failure(school)
        self.assertTrue(ok)
        # No FAILED event should land on the happy path.
        self.assertFalse(
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.FAILED,
            ).exists()
        )
