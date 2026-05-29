"""Phase 4F — staff compliance registry tests."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.people.staff_compliance import (
    StaffComplianceRecord,
    attendance_allowed_for_teacher,
)


class StaffComplianceRecordTests(SimpleTestCase):
    def test_valid_when_no_expiry(self):
        record = StaffComplianceRecord(is_cleared=True, expires_on=None)
        self.assertTrue(record.is_valid_on(date.today()))

    def test_invalid_when_expired(self):
        record = StaffComplianceRecord(
            is_cleared=True,
            expires_on=date.today() - timedelta(days=1),
        )
        self.assertFalse(record.is_valid_on(date.today()))


class AttendanceGateTests(SimpleTestCase):
    @patch("apps.people.staff_compliance.StaffComplianceRecord.objects")
    def test_blocks_when_safeguarding_expired(self, mock_objects):
        teacher = SimpleNamespace(pk=1)
        expired = StaffComplianceRecord(
            clearance_type=StaffComplianceRecord.ClearanceType.SAFEGUARDING,
            is_cleared=True,
            expires_on=date.today() - timedelta(days=2),
        )
        expired.pk = 7
        mock_objects.filter.return_value.exists.return_value = True
        mock_objects.filter.return_value.__iter__ = MagicMock(return_value=iter([expired]))

        allowed, reason = attendance_allowed_for_teacher(teacher)
        self.assertFalse(allowed)
        self.assertIn("clearance_expired", reason)

    @patch("apps.people.staff_compliance.StaffComplianceRecord.objects")
    def test_allows_when_no_records(self, mock_objects):
        teacher = SimpleNamespace(pk=2)
        mock_objects.filter.return_value.exists.return_value = False
        allowed, reason = attendance_allowed_for_teacher(teacher)
        self.assertTrue(allowed)
        self.assertEqual(reason, "no_safeguarding_requirement")
