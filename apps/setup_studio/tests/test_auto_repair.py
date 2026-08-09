"""Setup Studio auto-repair — the real "Fix automatically" behaviour.

Regression guard: before this, "Fix automatically" only recomputed the health
score, so it never changed. These tests prove auto-repair actually performs
safe setup (attaches the default plan, creates a starter academic year, aligns
localization registries) and reports what still needs a human.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.registries.models import CountryRegistry
from apps.siteconfig.models_platform_catalog import Plan
from apps.schools.models import School
from apps.setup_studio.auto_repair import auto_repair_setup


class AutoRepairSetupTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        Plan.objects.create(
            name="Free Starter",
            slug="free-starter-autorepair",
            base_price=Decimal("0.00"),
            is_active=True,
            is_default=True,
        )
        self.school = School.objects.create(
            name="Repair School",
            slug="repair-school",
            subdomain="repair-school",
            country_code="CM",
            timezone="",  # blank on purpose so auto-repair derives it
            is_active=True,
        )

    def test_auto_repair_raises_health_and_performs_setup(self):
        self.assertIsNone(self.school.plan_id)
        self.assertFalse(AcademicYear.objects.filter(school=self.school).exists())

        report = auto_repair_setup(self.school, actor_id=7)

        self.assertTrue(report["ok"])
        # It performed real work, not just a recompute.
        self.assertGreater(report["fixed_count"], 0)
        self.assertGreater(report["health_after"], report["health_before"])

        # Default plan attached.
        self.school.refresh_from_db()
        self.assertIsNotNone(self.school.plan_id)
        # Starter academic year created.
        self.assertTrue(AcademicYear.objects.filter(school=self.school).exists())
        # Timezone derived from the country default (was blank).
        self.assertTrue(self.school.timezone)
        self.assertTrue(report["run_id"])
        self.assertEqual(
            self.school.settings["setup_repair_history"][-1]["run_id"],
            report["run_id"],
        )

        # The genuinely-human steps are reported, not silently performed.
        human_keys = {step["key"] for step in report["needs_human"]}
        self.assertIn("blueprint", human_keys)
        self.assertIn("data_path", human_keys)

    def test_auto_repair_is_idempotent(self):
        first = auto_repair_setup(self.school)
        year_count = AcademicYear.objects.filter(school=self.school).count()
        plan_id = self.school.plan_id
        second = auto_repair_setup(self.school)
        # No duplicate academic year, plan unchanged, score stable.
        self.assertEqual(
            AcademicYear.objects.filter(school=self.school).count(), year_count
        )
        self.assertEqual(self.school.plan_id, plan_id)
        self.assertEqual(second["health_after"], first["health_after"])

    def test_registry_seed_failure_is_reported_honestly(self):
        with patch(
            "apps.registries.services.ensure_registry_baseline",
            side_effect=RuntimeError("seed unavailable"),
        ):
            report = auto_repair_setup(self.school)
        self.assertGreater(report["warning_count"], 0)
        self.assertTrue(
            any("could not be verified" in warning for warning in report["warnings"])
        )
        self.assertTrue(
            any(action["assessment"] == "check_manually" for action in report["actions"])
        )

    def test_registry_mismatch_becomes_guided_remediation(self):
        self.school.timezone = "Invalid/School-Time"
        self.school.save(update_fields=["timezone", "updated_at"])
        report = auto_repair_setup(self.school)
        registry_steps = [
            step for step in report["needs_human"] if step["key"] == "registry_alignment"
        ]
        self.assertEqual(len(registry_steps), 1)
        self.assertTrue(registry_steps[0]["fields"])
        step = registry_steps[0]
        self.assertIn("repair_field=timezone", step["cta_url"])
        self.assertIn("#repair-editor", step["cta_url"])
        self.assertEqual(step["cta_url"], step["fields"][0]["cta_url"])
        self.assertNotEqual(step["cta_url"], "/school/settings/")
