"""Governor cockpit usage counters read their AUTHORITATIVE sources (2026-08-10).

`get_governor_usage_for_tenant` previously hardcoded `active_migrations`,
`dynamic_field_count`, and `ai_invocations_today` to 0, so the operator runtime
cockpit always rendered "0 / limit" regardless of real activity. They are now
wired — WITHOUT building parallel counters — to the authoritative sources that
already exist:

  * ai_invocations   -> billing UsageMeter daily rollup (models_metering.snapshot)
  * dynamic_field_count -> active metadata.DynamicFieldDefinition rows
  * active_migrations   -> migration_cloud bundles in the APPLYING state

This is the must-fire guard: it proves each counter reflects a real row AND that
an unresolvable / absent school degrades every counter to 0 rather than raising
into the cockpit render.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings

from apps.platform_runtime.governor_limits import (
    AI_INVOCATIONS_PER_DAY_PER_TENANT,
    DYNAMIC_FIELD_COUNT_MAX_PER_TENANT,
    MIGRATION_CONCURRENCY_PER_TENANT,
    get_governor_usage_for_tenant,
)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class GovernorUsageWiringTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        from apps.siteconfig.models import Plan
        from apps.siteconfig.models_platform_catalog import RegionConfig

        cls.plan = Plan.objects.create(
            name="Gov", slug="gov", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="GV", name="Govland", timezone="UTC", default_currency="USD"
        )

    def setUp(self):
        from apps.schools.models import School

        slug = f"gov-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name=f"Gov School {slug}",
            slug=slug,
            subdomain=slug,
            is_active=True,
            plan=self.plan,
            default_region=self.region,
            settings={},
        )

    def _status(self):
        return get_governor_usage_for_tenant(
            tenant_id=str(self.school.id), school_id=self.school.id
        )["status"]

    def test_ai_invocations_reads_billing_meter(self):
        from apps.billing.models_metering import record

        record(self.school, "ai_invocations", delta=3)
        s = self._status()["ai_invocations_per_day"]
        self.assertEqual(s["used"], 3)
        self.assertEqual(s["limit"], AI_INVOCATIONS_PER_DAY_PER_TENANT)

    def test_dynamic_field_count_reads_active_definitions(self):
        from apps.metadata.models import DynamicFieldDefinition

        DynamicFieldDefinition.objects.create(
            entity_type="student", field_key="preferred_name",
            school=self.school, is_active=True,
        )
        DynamicFieldDefinition.objects.create(
            entity_type="student", field_key="bus_route",
            school=self.school, is_active=True,
        )
        # An inactive definition must not be counted against the cap.
        DynamicFieldDefinition.objects.create(
            entity_type="student", field_key="retired_field",
            school=self.school, is_active=False,
        )
        s = self._status()["dynamic_field_count_max"]
        self.assertEqual(s["used"], 2)
        self.assertEqual(s["limit"], DYNAMIC_FIELD_COUNT_MAX_PER_TENANT)

    def test_active_migrations_counts_only_applying_bundles(self):
        from apps.migration_cloud.models import BundleStatus, MigrationBundle

        MigrationBundle.objects.create(
            school=self.school,
            status=BundleStatus.APPLYING,
            idempotency_key=f"applying-{uuid.uuid4().hex}",
        )
        # A bundle that is merely READY (not in-flight) must not count.
        MigrationBundle.objects.create(
            school=self.school,
            status=BundleStatus.READY,
            idempotency_key=f"ready-{uuid.uuid4().hex}",
        )
        s = self._status()["migration_concurrency"]
        self.assertEqual(s["used"], 1)
        self.assertEqual(s["limit"], MIGRATION_CONCURRENCY_PER_TENANT)

    def test_unresolvable_school_degrades_to_zero_without_error(self):
        s = get_governor_usage_for_tenant(
            tenant_id=str(uuid.uuid4()), school_id=uuid.uuid4()
        )["status"]
        self.assertEqual(s["ai_invocations_per_day"]["used"], 0)
        self.assertEqual(s["dynamic_field_count_max"]["used"], 0)
        self.assertEqual(s["migration_concurrency"]["used"], 0)

    def test_no_school_context_is_zero(self):
        s = get_governor_usage_for_tenant()["status"]
        self.assertEqual(s["ai_invocations_per_day"]["used"], 0)
        self.assertEqual(s["dynamic_field_count_max"]["used"], 0)
        self.assertEqual(s["migration_concurrency"]["used"], 0)
