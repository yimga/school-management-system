"""COPPA parity for the LEGACY session-driven student self-onboarding branch.

The Unified-engine path (operator producer -> create_student_from_wizard applier)
classifies a student's DOB under the school-as-agent basis and never persists the
raw date of birth. The legacy `?legacy=1` session flow used to bypass both: it
called StudentProfile.objects.create(date_of_birth=...) directly, storing raw DOB
and skipping the gate — contradicting the SOC2 P3.1 claim that "every account-
creation path is school/operator-mediated ... raw date of birth is never stored."

These seals lock the fix:
  * the shared classifier is WIRED into the legacy branch, and
  * the legacy branch NEVER persists raw DOB (data minimisation).
`test_legacy_branch_does_not_persist_raw_dob` is the must-fire seal — it fails on
the pre-fix source (which passed `date_of_birth=` to the model create).
"""

import datetime as dt
import inspect

from django.test import SimpleTestCase

from apps.portal.services_student_onboarding import classify_self_onboarding_dob
from apps.portal import views_onboarding


class SelfOnboardingCoppaHelperTests(SimpleTestCase):
    def test_minor_dob_is_classified_minor_and_allowed_under_school_agent(self):
        today = dt.date.today()
        dob = dt.date(today.year - 10, 6, 15)  # 9-10 y/o regardless of birthday
        decision = classify_self_onboarding_dob(dob)
        self.assertTrue(decision.is_minor)
        # School-as-agent basis permits the minor (parity with the engine path).
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.age_band, "minor")

    def test_adult_dob_is_classified_adult(self):
        today = dt.date.today()
        dob = dt.date(today.year - 30, 6, 15)
        decision = classify_self_onboarding_dob(dob)
        self.assertFalse(decision.is_minor)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.age_band, "adult")

    def test_missing_dob_is_non_blocking(self):
        decision = classify_self_onboarding_dob(None)
        self.assertIsNone(decision.is_minor)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.age_band, "unknown")


class SelfOnboardingCoppaViewSealTests(SimpleTestCase):
    """Source-level regression seals on the legacy create branch."""

    def _src(self) -> str:
        return inspect.getsource(views_onboarding.student_onboarding_wizard)

    def test_legacy_branch_wires_the_coppa_classifier(self):
        self.assertIn(
            "classify_self_onboarding_dob(",
            self._src(),
            "The legacy self-onboarding create must classify the DOB via the "
            "shared COPPA helper (parity with the Unified-engine path).",
        )

    def test_legacy_branch_does_not_persist_raw_dob(self):
        # Must-fire: pre-fix the create passed date_of_birth=form.cleaned_data...;
        # raw DOB must never be persisted on a self-onboarding pre-registration
        # profile — classify then drop it, exactly like create_student_from_wizard.
        self.assertNotIn(
            "date_of_birth=",
            self._src(),
            "Self-onboarding must not persist raw date_of_birth (data "
            "minimisation): classify the age, then drop the raw DOB.",
        )
