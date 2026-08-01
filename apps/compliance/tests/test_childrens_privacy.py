"""M19 children's-privacy (COPPA) age-gate — primitive + real producer/applier.

Covers:
  * the pure classification primitive (age derivation edges + gate branches),
  * the applier: ``create_student_from_wizard`` refuses a minor payload with no
    consent basis but allows an operator/school-mediated one,
  * the producer: ``write_student_self_onboarding_step`` stamps the minor
    classification and never forwards the raw date of birth,
  * the SOC2 register wiring of the new children's-privacy control.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.compliance.childrens_privacy import (
    ConsentBasis,
    consent_basis_is_sufficient_for_minor,
    coppa_min_age,
    derive_age,
    evaluate_coppa_gate,
)

_TODAY = dt.date(2026, 7, 31)


class ChildrensPrivacyPrimitiveTests(SimpleTestCase):
    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_min_age_from_settings(self):
        self.assertEqual(coppa_min_age(), 13)

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=0)
    def test_min_age_non_positive_falls_back_to_default(self):
        self.assertEqual(coppa_min_age(), 13)

    def test_derive_age_birthday_edges(self):
        # Turns 13 exactly on the reference day → 13 (not a minor at threshold).
        self.assertEqual(derive_age("2013-07-31", today=_TODAY), 13)
        # One day before the 13th birthday → still 12 (a minor).
        self.assertEqual(derive_age("2013-08-01", today=_TODAY), 12)
        self.assertEqual(derive_age("1986-01-15", today=_TODAY), 40)

    def test_derive_age_leap_and_types(self):
        self.assertEqual(derive_age("2012-02-29", today=_TODAY), 14)
        self.assertEqual(derive_age(dt.date(2015, 7, 31), today=_TODAY), 11)
        self.assertEqual(derive_age(dt.datetime(2015, 7, 31, 9, 0), today=_TODAY), 11)

    def test_derive_age_absent_or_bad(self):
        self.assertIsNone(derive_age("", today=_TODAY))
        self.assertIsNone(derive_age(None, today=_TODAY))
        self.assertIsNone(derive_age("not-a-date", today=_TODAY))
        # Future DOB (clock skew / typo) → None, never negative.
        self.assertIsNone(derive_age("2030-01-01", today=_TODAY))

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_gate_adult_allowed_without_basis(self):
        d = evaluate_coppa_gate(age=15, consent_basis=ConsentBasis.NONE)
        self.assertTrue(d.allowed)
        self.assertFalse(d.is_minor)
        self.assertFalse(d.requires_guardian_consent)
        self.assertEqual(d.age_band, "adult")

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_gate_minor_without_basis_blocked(self):
        d = evaluate_coppa_gate(age=11, consent_basis=ConsentBasis.NONE)
        self.assertFalse(d.allowed)
        self.assertTrue(d.is_minor)
        self.assertTrue(d.requires_guardian_consent)
        self.assertEqual(d.reason, "minor_requires_consent")

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_gate_minor_with_school_authorization_allowed(self):
        d = evaluate_coppa_gate(
            age=11, consent_basis=ConsentBasis.SCHOOL_AUTHORIZATION
        )
        self.assertTrue(d.allowed)
        self.assertTrue(d.is_minor)
        self.assertFalse(d.requires_guardian_consent)

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_gate_minor_with_guardian_consent_string_allowed(self):
        d = evaluate_coppa_gate(age=11, consent_basis="guardian_consent")
        self.assertTrue(d.allowed)
        self.assertTrue(d.is_minor)

    @override_settings(COPPA_SELF_SERVICE_MIN_AGE=13)
    def test_gate_bogus_basis_treated_as_none(self):
        self.assertFalse(evaluate_coppa_gate(age=11, consent_basis="bogus").allowed)

    def test_gate_unknown_age_non_blocking(self):
        # School flows legitimately omit DOB → not blocked, classification unknown.
        d = evaluate_coppa_gate(age=None, consent_basis=ConsentBasis.NONE)
        self.assertTrue(d.allowed)
        self.assertIsNone(d.is_minor)
        self.assertEqual(d.age_band, "unknown")

    def test_consent_basis_predicate(self):
        self.assertTrue(
            consent_basis_is_sufficient_for_minor(ConsentBasis.SCHOOL_AUTHORIZATION)
        )
        self.assertTrue(consent_basis_is_sufficient_for_minor("guardian_consent"))
        self.assertFalse(consent_basis_is_sufficient_for_minor(ConsentBasis.NONE))
        self.assertFalse(consent_basis_is_sufficient_for_minor(""))
        self.assertFalse(consent_basis_is_sufficient_for_minor(None))


def _school():
    from apps.schools.models import School

    return School.objects.create(
        name="coppa-school", slug="coppa-school", subdomain="coppa-school", is_active=True
    )


class StudentOnboardingCoppaGateTests(TestCase):
    """The applier: create_student_from_wizard enforces the consent basis."""

    def setUp(self):
        self.school = _school()

    def _create(self, payload):
        from apps.portal.services_student_onboarding import create_student_from_wizard

        return create_student_from_wizard(
            school=self.school, actor_user_id=None, wizard_payload=payload
        )

    def test_minor_without_basis_is_refused(self):
        from apps.people.models import StudentProfile

        r = self._create(
            {"first_name": "Kid", "last_name": "NoBasis", "is_minor": True}
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "coppa_consent_required")
        self.assertFalse(
            StudentProfile.objects.filter(
                school=self.school, last_name="NoBasis"
            ).exists()
        )

    def test_minor_with_school_authorization_is_allowed(self):
        from apps.people.models import StudentProfile

        r = self._create(
            {
                "first_name": "Kid",
                "last_name": "Authorized",
                "is_minor": True,
                "coppa_consent_basis": ConsentBasis.SCHOOL_AUTHORIZATION.value,
            }
        )
        self.assertTrue(r["ok"], r)
        self.assertTrue(
            StudentProfile.objects.filter(pk=r["student_profile_id"]).exists()
        )

    def test_adult_or_unknown_age_unaffected(self):
        # Regression guard: the existing (no is_minor) path still works.
        r = self._create({"first_name": "Stu", "last_name": "Dent"})
        self.assertTrue(r["ok"], r)


class SelfOnboardingStepClassificationTests(SimpleTestCase):
    """The producer: the step stamps the minor flag and drops the raw DOB."""

    def _run_step(self, dob_iso):
        from apps.setup_studio import wizard_resolvers_operator as wro

        captured = {}

        def _fake_create(*, school, wizard_payload, actor_user_id=None):
            captured["payload"] = wizard_payload
            return {"ok": True}

        with mock.patch.object(wro, "_default_cockpit_writer", lambda **kw: None), \
                mock.patch(
                    "apps.portal.services_student_onboarding.create_student_from_wizard",
                    _fake_create,
                ):
            wro.write_student_self_onboarding_step(
                school=SimpleNamespace(pk=7),
                wizard_key="student_self_onboarding",
                step_key="profile_photo",
                payload={
                    "first_name": "Kid",
                    "last_name": "Minor",
                    "date_of_birth": dob_iso,
                },
                actor_user_id=1,
            )
        return captured.get("payload", {})

    def test_minor_dob_stamps_classification_and_drops_raw_dob(self):
        today = dt.date.today()
        minor_dob = dt.date(today.year - 8, 1, 1).isoformat()
        payload = self._run_step(minor_dob)
        self.assertTrue(payload.get("is_minor"))
        self.assertEqual(payload.get("coppa_age_band"), "minor")
        self.assertEqual(
            payload.get("coppa_consent_basis"),
            ConsentBasis.SCHOOL_AUTHORIZATION.value,
        )
        # Data minimisation: the raw DOB is never forwarded, only the hash.
        self.assertNotIn("date_of_birth", payload)
        self.assertIn("date_of_birth_hash", payload)

    def test_adult_dob_not_flagged_minor(self):
        today = dt.date.today()
        adult_dob = dt.date(today.year - 30, 1, 1).isoformat()
        payload = self._run_step(adult_dob)
        self.assertFalse(payload.get("is_minor"))
        self.assertEqual(payload.get("coppa_age_band"), "adult")
        self.assertNotIn("date_of_birth", payload)


class Soc2ChildrensPrivacyControlTests(SimpleTestCase):
    def test_control_registered_with_resolving_evidence(self):
        from django.apps import apps as django_apps

        from apps.compliance.soc2_control_register import get_control

        c = get_control("P3.1")
        self.assertIsNotNone(c)
        self.assertEqual(c.category, "privacy")
        self.assertEqual(c.status, "implemented")
        # The evidence model must load (mirrors the lane-2 readiness contract).
        app_label, model_name = c.evidence_model.split(".", 1)
        self.assertIsNotNone(django_apps.get_model(app_label, model_name))
