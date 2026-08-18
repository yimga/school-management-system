"""A payroll file that names its staff must import.

``payroll`` required a non-empty ``staff_external_id`` and offered no name field
at all, so a school that kept payroll by name -- the same schools whose roster
has no student id -- had every row rejected with "missing staff_external_id".

The lander does not resolve a staff FK; it writes a record keyed on
(person, pay period). A name is a perfectly good identity for that. It simply
was not accepted.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.payroll_lander import PayrollLander
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY
from apps.schools.models import School


class PayrollNamedStaffTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Payroll School",
            slug="payroll-school",
            subdomain="payroll-school",
            is_active=True,
        )
        self.ctx = LanderContext(
            school=self.school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
        )

    def test_the_domain_offers_a_staff_name(self):
        self.assertIn("staff_name", CANONICAL_ONTOLOGY["payroll"])

    def test_a_row_naming_the_staff_member_is_accepted(self):
        result = PayrollLander().land(
            canonical_rows=iter(
                [{"staff_name": "NGONO Marie", "pay_period": "2026-01", "gross_pay": "150000"}]
            ),
            ctx=self.ctx,
        )
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 1)

    def test_a_row_naming_nobody_is_still_rejected_with_a_usable_reason(self):
        result = PayrollLander().land(
            canonical_rows=iter([{"pay_period": "2026-01", "gross_pay": "150000"}]),
            ctx=self.ctx,
        )
        self.assertEqual(result.quarantined, 1)
        joined = " ".join(result.errors)
        self.assertIn("staff name column", joined)
        self.assertNotIn("staff_external_id", joined)

    def test_re_running_the_same_named_row_does_not_duplicate(self):
        rows = [{"staff_name": "NGONO Marie", "pay_period": "2026-01", "gross_pay": "1"}]
        PayrollLander().land(canonical_rows=iter(list(rows)), ctx=self.ctx)
        from apps.metadata.models import DynamicFieldValue

        first = DynamicFieldValue.objects.count()
        PayrollLander().land(canonical_rows=iter(list(rows)), ctx=self.ctx)
        self.assertEqual(
            DynamicFieldValue.objects.count(),
            first,
            "a re-run created a second payroll record for the same person/period",
        )
