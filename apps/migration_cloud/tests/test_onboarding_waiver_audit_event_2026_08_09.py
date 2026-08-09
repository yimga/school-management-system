"""Seal: onboarding waivers append a tamper-evident audit-chain event (2026-08-09).

Beyond the durable settings ``history`` trail, every waive / un-waive now also
records a hash-chained MigrationCloudAuditEvent so the decision is forgery-evident
alongside the rest of the tenant's migration audit log.

These tests FAIL before onboarding_waiver emits the audit event (and before the
ONBOARDING_WAIVER_* event types are registered).
"""
from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _hash_tenant_slug,
)
from apps.schools.models import School
from apps.schools import onboarding_waiver as ow


class WaiverAuditEventTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Audit Waiver School",
            slug="audit-waiver",
            subdomain="audit-waiver",
            is_active=True,
            country_code="CM",
        )
        self.tenant_hash = _hash_tenant_slug("audit-waiver")

    def _events(self, event_type):
        return MigrationCloudAuditEvent.objects.filter(
            tenant_id_hash=self.tenant_hash, event_type=event_type
        )

    def test_waive_emits_applied_event(self):
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_NO_LEGACY_DATA)
        evs = self._events(
            MigrationCloudAuditEventType.ONBOARDING_WAIVER_APPLIED.value
        )
        self.assertEqual(evs.count(), 1)
        ev = evs.first()
        self.assertEqual(ev.payload_summary.get("kind"), "migration")
        self.assertEqual(ev.payload_summary.get("state"), ow.STATE_WAIVED)
        # Hash-chained (tamper-evident).
        self.assertTrue(ev.integrity_hash)

    def test_unwaive_emits_reversed_event(self):
        ow.waive(self.school, ow.WAIVER_ROSTER)
        ow.unwaive(self.school, ow.WAIVER_ROSTER)
        self.assertEqual(
            self._events(
                MigrationCloudAuditEventType.ONBOARDING_WAIVER_REVERSED.value
            ).count(),
            1,
        )

    def test_event_types_are_registered_choices(self):
        valid = {c.value for c in MigrationCloudAuditEventType}
        self.assertIn("onboarding.waiver.applied", valid)
        self.assertIn("onboarding.waiver.reversed", valid)
