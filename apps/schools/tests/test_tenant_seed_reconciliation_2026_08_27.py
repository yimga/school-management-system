from copy import deepcopy

from django.core.management import call_command
from django.test import TestCase

from apps.registries.services import ensure_registry_baseline
from apps.schools.models import School
from apps.schools.seed_reconciliation import (
    _merge_missing,
    reconcile_tenant_seed_baseline,
)
from apps.siteconfig.models import EducationSystemProfile, Plan


class MergeMissingTests(TestCase):
    def test_blank_default_does_not_report_a_false_change(self):
        target = {"localization": {"code_prefix": ""}}
        before = deepcopy(target)

        changed = _merge_missing(
            target, {"localization": {"code_prefix": ""}}
        )

        self.assertFalse(changed)
        self.assertEqual(target, before)

    def test_manual_values_win_while_absent_values_are_added(self):
        target = {"localization": {"language_code": "fr"}}

        changed = _merge_missing(
            target,
            {
                "localization": {
                    "language_code": "en",
                    "calendar_code": "gregorian",
                }
            },
        )

        self.assertTrue(changed)
        self.assertEqual(target["localization"]["language_code"], "fr")
        self.assertEqual(target["localization"]["calendar_code"], "gregorian")


class TenantSeedReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_registry_baseline()
        call_command("seed_subscription_catalog", verbosity=0)

    def test_missing_tenant_baseline_is_filled_and_second_run_is_noop(self):
        school = School.objects.create(
            name="Technical Seed School",
            slug="technical-seed-school",
            subdomain="technical-seed-school",
            country_code="CM",
            school_type="TECHNICAL_COLLEGE",
            timezone="",
            default_language="",
            currency="",
            settings={},
        )

        first = reconcile_tenant_seed_baseline(school)
        school.refresh_from_db()

        self.assertTrue(first.changed)
        self.assertTrue(school.default_region_id)
        self.assertTrue(school.plan_id)
        self.assertIn(
            "TECHNICAL",
            set(school.education_system_types.values_list("code", flat=True)),
        )
        self.assertEqual(
            set(school.education_levels.values_list("code", flat=True)),
            {"SECONDARY", "TERTIARY"},
        )
        profile_code = school.settings.get("education_profile_code")
        self.assertTrue(
            EducationSystemProfile.objects.filter(
                code=profile_code,
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            ).exists()
        )

        second = reconcile_tenant_seed_baseline(school)
        self.assertFalse(second.changed)

    def test_explicit_plan_classification_and_localization_are_preserved(self):
        explicit_plan = Plan.objects.create(
            slug="explicit-enterprise-plan",
            name="Explicit Enterprise",
            base_price="1.00",
            is_active=True,
            is_default=False,
        )
        school = School.objects.create(
            name="Manual Choice School",
            slug="manual-choice-school",
            subdomain="manual-choice-school",
            country_code="US",
            plan=explicit_plan,
            primary_sector="PUBLIC",
            settings={"localization": {"language_code": "es"}},
        )
        ensure_registry_baseline()
        from apps.registries.models import (
            EducationLevelRegistry,
            EducationSystemTypeRegistry,
        )

        school.education_system_types.set(
            [EducationSystemTypeRegistry.objects.get(code="PUBLIC")]
        )
        school.education_levels.set(
            [EducationLevelRegistry.objects.get(code="TERTIARY")]
        )

        reconcile_tenant_seed_baseline(school)
        school.refresh_from_db()

        self.assertEqual(school.plan_id, explicit_plan.pk)
        self.assertEqual(school.primary_sector, "PUBLIC")
        self.assertEqual(school.settings["localization"]["language_code"], "es")
        self.assertEqual(
            set(school.education_system_types.values_list("code", flat=True)),
            {"PUBLIC"},
        )
        self.assertEqual(
            set(school.education_levels.values_list("code", flat=True)),
            {"TERTIARY"},
        )
