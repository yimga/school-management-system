"""Wizard POS / observability / scheduling domain writer tests."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.platform_runtime.models import RuntimeDefaults
from apps.registries.models import CountryRegistry
from apps.schoolops.models import MealPlanBalance
from apps.schoolops.pos_checkout import ALLERGEN_RULES_SETTING
from apps.schools.models import School
from apps.setup_studio.wizard_resolvers import (
    write_observability_thresholds,
    write_pos_allergens,
    write_pos_guardrails,
    write_scheduling_resources,
    write_scheduling_solver,
)


class PosWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="POS School",
            slug="pos-school",
            subdomain="pos-school",
            country_code="US",
            is_active=True,
        )
        from apps.people.models import StudentProfile

        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Test",
            last_name="Student",
            student_code="POS001",
        )
        MealPlanBalance.objects.create(
            school=self.school,
            student=self.student,
            balance=Decimal("50.00"),
            low_balance_threshold=Decimal("2.00"),
        )

    def test_guardrails_update_wallets(self):
        write_pos_guardrails(
            school=self.school,
            wizard_key="cashless_campus_pos",
            step_key="daily_guardrails",
            payload={
                "parent_default_daily_limit_decimal": "25.00",
                "top_up_minimum": "5.00",
                "top_up_maximum": "150.00",
                "low_balance_threshold": "10.00",
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        pos = (self.school.settings or {}).get("pos", {})
        self.assertEqual(pos["guardrails"]["low_balance_threshold"], "10.00")
        wallet = MealPlanBalance.objects.get(student=self.student)
        self.assertEqual(wallet.low_balance_threshold, Decimal("10.00"))

    def test_allergen_rules_readable_by_checkout(self):
        write_pos_allergens(
            school=self.school,
            wizard_key="cashless_campus_pos",
            step_key="allergen_dietary_rules",
            payload={"value": True},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        rules = (self.school.settings or {}).get(ALLERGEN_RULES_SETTING, {})
        self.assertTrue(rules.get("enabled"))


class ObservabilityWriterTests(TestCase):
    def test_platform_thresholds_without_school(self):
        write_observability_thresholds(
            school=None,
            wizard_key="self_healing_observability_guard",
            step_key="threshold_definition",
            payload={
                "error_rate_threshold_pct": "1.5",
                "latency_p95_threshold_ms": "800",
                "uptime_target_pct": "99.9",
            },
            actor_user_id=1,
        )
        rd = RuntimeDefaults.objects.get(pk=1)
        guard = (rd.payload or {}).get("observability_guard", {})
        self.assertIn("slo_merge", guard)
        self.assertEqual(guard["thresholds"]["uptime_target_pct"], "99.9")


class SchedulingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Sched School",
            slug="sched-school",
            subdomain="sched-school",
            country_code="CM",
            is_active=True,
        )

    def test_resource_constraints_persist(self):
        write_scheduling_resources(
            school=self.school,
            wizard_key="dynamic_multi_campus_scheduling",
            step_key="resource_constraints",
            payload={"pairs": [{"key": "max_daily_lessons", "value": "6"}]},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        sched = (self.school.settings or {}).get("scheduling", {})
        self.assertEqual(len(sched.get("resource_constraints", [])), 1)

    def test_solver_enqueues_celery(self):
        with mock.patch("apps.academics.tasks_scheduling.run_scheduling_solver_task.delay") as delay:
            write_scheduling_solver(
                school=self.school,
                wizard_key="dynamic_multi_campus_scheduling",
                step_key="ai_conflict_solver",
                payload={"value": True},
                actor_user_id=1,
            )
            delay.assert_called_once_with(int(self.school.pk))
        self.school.refresh_from_db()
        self.assertTrue((self.school.settings or {}).get("scheduling", {}).get("ai_conflict_solver"))
