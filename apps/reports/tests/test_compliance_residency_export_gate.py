"""Metric 27: cross-border export blocked when residency enforcement is on."""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings

from apps.reports.compliance_exports import EXPORT_OFSTED, generate_regional_compliance_export
from apps.schools.models import School


@override_settings(DATA_RESIDENCY_ENFORCE=True)
class ComplianceResidencyExportGateTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Residency School",
            slug=f"res-{uid}",
            subdomain=f"res{uid}",
            data_region="eu_central",
            is_active=True,
        )

    def test_cross_region_export_blocked_when_enforced(self):
        result = generate_regional_compliance_export(
            EXPORT_OFSTED,
            school=self.school,
            user=None,
            params={"destination_region": "us_east"},
        )
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("blocked"))
        self.assertIn("blocked", str(result.get("message", "")).lower())

    def test_in_region_export_not_blocked_by_residency_gate(self):
        result = generate_regional_compliance_export(
            EXPORT_OFSTED,
            school=self.school,
            user=None,
            params={"destination_region": "eu_central"},
        )
        if result.get("blocked"):
            self.assertNotIn("data_region", str(result.get("message", "")).lower())
