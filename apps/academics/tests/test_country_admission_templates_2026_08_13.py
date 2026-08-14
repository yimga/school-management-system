"""Increment (f) — country-default admission-number templates.

The policy cascade advertised platform ⊕ country ⊕ tenant, but the country
admission layer was empty (RegionConfig.student_id_format shipped blank), so every
tenant fell back to the generic {yy}{code}{seq}{spec}{class} format. These tests
pin: the curated table + region-format resolve correctly; a FRESH tenant gets its
country template applied to a real TenantAdmissionNumberPolicy (and preview uses
it); and the two safety guards (existing policy / already-issued numbers) prevent
ever changing a school's format under it.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.structure_provisioning import ensure_admission_template
from apps.policies.country_admission_templates import (
    resolve_admission_template,
    template_for_country,
)
from apps.schools.models import School


class TemplateResolveTests(TestCase):
    def test_curated_country_codes_alpha2_and_alpha3(self):
        self.assertEqual(template_for_country("CM"), "{school_code}/{year_2digit}/{seq_4digit}")
        self.assertEqual(template_for_country("CMR"), "{school_code}/{year_2digit}/{seq_4digit}")
        self.assertEqual(template_for_country("US"), "{year_2digit}{seq_4digit}")
        # unknown → generic
        self.assertEqual(template_for_country("XX"), "{year_2digit}{school_code}{seq_4digit}")
        self.assertEqual(template_for_country(""), "{year_2digit}{school_code}{seq_4digit}")

    def test_region_student_id_format_overrides_catalog(self):
        school = School.objects.create(name="Rg", subdomain="rg-adm", country_code="CM")
        # CMR region's student_id_format was seeded by migration 0209 → it wins over
        # the bare catalog (they happen to match for CM; assert a real value returns).
        self.assertTrue(resolve_admission_template(school))
        # Explicit region override is honored.
        region = school.default_region
        if region is not None:
            region.student_id_format = "CUSTOM-{seq_4digit}"
            region.save(update_fields=["student_id_format"])
            school.refresh_from_db()
            self.assertEqual(resolve_admission_template(school), "CUSTOM-{seq_4digit}")


class EnsureAdmissionTemplateTests(TestCase):
    def test_fresh_school_gets_country_policy_and_preview_uses_it(self):
        from apps.siteconfig.identifier_policy_service import preview_admission_number
        from apps.siteconfig.models import TenantAdmissionNumberPolicy

        school = School.objects.create(name="Fr", subdomain="fr-adm", country_code="CM")
        result = ensure_admission_template(school)
        self.assertIn("template", result)

        policy = TenantAdmissionNumberPolicy.objects.filter(school=school).first()
        self.assertIsNotNone(policy)
        self.assertEqual(policy.strategy, "TEMPLATE")
        # The generator renders the country template (slash form), not the generic
        # {yy}{code}{seq}{spec}{class}.
        preview = preview_admission_number(school, year_2digit="26", seq_4digit="0001")
        self.assertIn("/26/", preview)
        self.assertIn("/0001", preview)

    def test_existing_policy_is_never_replaced(self):
        from apps.siteconfig.models import TenantAdmissionNumberPolicy

        school = School.objects.create(name="Ex", subdomain="ex-adm", country_code="CM")
        TenantAdmissionNumberPolicy.objects.create(
            school=school, strategy="FULL", school_code="EX", is_active=True
        )
        result = ensure_admission_template(school)
        self.assertEqual(result.get("skipped"), "policy_exists")
        self.assertEqual(
            TenantAdmissionNumberPolicy.objects.get(school=school).strategy, "FULL"
        )

    def test_already_issued_numbers_block_the_default(self):
        school = School.objects.create(name="Is", subdomain="is-adm", country_code="CM")
        # A student already stamped with a number → the school's format is frozen.
        from apps.people.models import StudentProfile

        s = StudentProfile.objects.create(school=school, first_name="A", last_name="B")
        StudentProfile.objects.filter(pk=s.pk).update(admission_number="26EX0001")

        result = ensure_admission_template(school)
        self.assertEqual(result.get("skipped"), "numbers_already_issued")
