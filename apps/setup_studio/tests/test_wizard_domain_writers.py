"""Wizard gate + domain writer integration tests."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio import wizard_engine, wizard_state_resolver
from apps.setup_studio.sovereignty_kernel import ensure_sovereignty_kernel_for_tenant, sovereignty_kernel_ready
from apps.setup_studio.wizard_gates import assert_wizard_gates, prerequisite_satisfied
from apps.setup_studio.wizard_resolvers import (
    write_alumni_programs,
    write_analytics_aggregation,
    write_fintech_split,
    write_marketplace_routing,
)


class SovereigntyKernelTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school",
            subdomain="gate-school",
            country_code="CM",
            is_active=True,
        )

    def test_seed_marks_prerequisite_complete(self):
        ensure_sovereignty_kernel_for_tenant(school=self.school)
        self.assertTrue(sovereignty_kernel_ready(self.school))
        self.assertTrue(
            prerequisite_satisfied(
                school=self.school,
                prerequisite_key="multi_campus_local_sovereignty",
            )
        )

    def test_fintech_wizard_passes_after_kernel_seed(self):
        ensure_sovereignty_kernel_for_tenant(school=self.school)
        wizard = wizard_engine.get_wizard("local_first_fintech_tax_matrix")
        assert_wizard_gates(wizard=wizard, school=self.school, request=None)

    def test_tenant_admin_bypasses_module_permission_gate(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin = User.objects.create_user(username="gate-admin", role=User.Role.ADMIN)
        request = type("R", (), {"user": admin})()
        wizard = wizard_engine.get_wizard("ai_helpcenter_knowledge_injection")
        assert_wizard_gates(wizard=wizard, school=self.school, request=request)


class DomainWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Writer School",
            slug="writer-school",
            subdomain="writer-school",
            country_code="US",
            is_active=True,
        )

    def test_fintech_split_persists_ppp(self):
        write_fintech_split(
            school=self.school,
            wizard_key="local_first_fintech_tax_matrix",
            step_key="revenue_split",
            payload={"base_usd": "100.00", "country_code": "US"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        split = (self.school.settings or {}).get("fintech", {}).get("ppp_revenue_split", {})
        self.assertEqual(split.get("currency_code"), "USD")
        self.assertIn("total", split)

    def test_marketplace_routing_ppp(self):
        write_marketplace_routing(
            school=self.school,
            wizard_key="localized_activity_asset_marketplace",
            step_key="payment_routing",
            payload={"base_usd": "25.00"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        mp = (self.school.settings or {}).get("marketplace_ppp", {})
        self.assertIn("last_localized_price", mp)

    def test_alumni_programs_enqueues_sync(self):
        with mock.patch("apps.people.tasks_alumni.sync_alumni_registry_task.delay") as delay:
            write_alumni_programs(
                school=self.school,
                wizard_key="alumni_engagement_pipeline",
                step_key="programs",
                payload={"value": ["mentorship", "reunion"]},
                actor_user_id=1,
            )
            delay.assert_called_once()
        self.school.refresh_from_db()
        alumni = (self.school.settings or {}).get("alumni_engagement", {})
        self.assertEqual(alumni.get("programs"), ["mentorship", "reunion"])

    def test_analytics_aggregation_board_snapshot(self):
        with mock.patch(
            "apps.reports.bi_services.ExecutiveReportingService.get_financial_summary",
            return_value={"revenue": Decimal("1000.00")},
        ):
            write_analytics_aggregation(
                school=self.school,
                wizard_key="institutional_performance_board_reporting",
                step_key="kpi_aggregation",
                payload={"value": ["enrollment", "finance"]},
                actor_user_id=1,
            )
        self.school.refresh_from_db()
        self.assertIn("board_reporting", self.school.settings or {})
