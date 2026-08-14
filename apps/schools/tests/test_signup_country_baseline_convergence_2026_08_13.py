"""Increment (h) — signup converges onto the shared country-baseline provisioner.

The migration path already flowed through provision_country_baseline; signup used
its own inline provisioning and so missed the newer country layers. After wiring
provision_country_baseline into _do_provision (and replacing the inline even-split
term loop with ensure_terms), a freshly-provisioned CM school now shows: real
per-country term DATES, national subject codes, a specialty↔subject curriculum,
and a country admission-number template — the SAME minimum defaults a migrated
school gets.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.academics.models import SpecialtySubject, Subject, Term
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class SignupCountryBaselineConvergenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Convergence Academy",
            slug="convergence-academy",
            subdomain="convergence-academy",
            country_code="CM",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(cls.school.id), contact_email="owner@conv.test")

    def test_terms_have_real_country_dates_not_even_split(self):
        terms = list(Term.objects.filter(school=self.school).order_by("position"))
        self.assertEqual(len(terms), 3, "Cameroon = 3 trimesters")
        # Real CM third trimester ends in July; the old inline even split said Aug.
        self.assertEqual(terms[2].end_date.month, 7)

    def test_subjects_carry_national_codes(self):
        subs = Subject.objects.filter(school=self.school)
        self.assertTrue(subs.exists(), "signup seeds a subject catalog")
        self.assertFalse(
            subs.filter(code="").exists(),
            "every provisioned subject should carry a national code",
        )

    def test_specialty_curriculum_is_seeded(self):
        self.assertTrue(
            SpecialtySubject.objects.filter(school=self.school).exists(),
            "the specialty↔subject curriculum should be seeded at signup",
        )

    def test_country_admission_template_is_applied(self):
        from apps.siteconfig.models import TenantAdmissionNumberPolicy

        policy = TenantAdmissionNumberPolicy.objects.filter(school=self.school).first()
        self.assertIsNotNone(policy, "a fresh school should get its country admission template")
        self.assertTrue(policy.template)
        self.assertEqual(policy.strategy, "TEMPLATE")
