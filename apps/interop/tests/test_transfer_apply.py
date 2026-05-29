"""Phase 4B — teacher transfer apply workflow tests."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.interop.transfer_apply import (
    TransferApplyError,
    apply_teacher_transfer_envelope,
    verify_envelope_checksum,
)
from apps.interop.transfer_envelope import build_teacher_envelope


class TransferApplyChecksumTests(SimpleTestCase):
    def test_verify_accepts_valid_envelope(self):
        envelope = build_teacher_envelope(
            source_tenant_id="source-tenant",
            target_tenant_id="target-tenant",
            canonical_data={},
        )
        verify_envelope_checksum(envelope)

    def test_verify_rejects_tampered_checksum(self):
        envelope = build_teacher_envelope(
            source_tenant_id="source-tenant",
            target_tenant_id="target-tenant",
            canonical_data={},
        )
        envelope.checksum = "deadbeef"
        with self.assertRaises(TransferApplyError):
            verify_envelope_checksum(envelope)


class TransferApplyWorkflowTests(SimpleTestCase):
    @patch("apps.governance.models.SchoolAssignment")
    @patch("apps.governance.models.Employment")
    @patch("apps.schools.models.School")
    def test_apply_creates_employment_and_assignment(self, mock_school, mock_employment, mock_assignment):
        school = SimpleNamespace(pk="school-b", organization_id="org-1", is_active=True)
        mock_school.objects.filter.return_value.first.return_value = school
        employment = SimpleNamespace(pk="emp-1")
        assignment = SimpleNamespace(pk="assign-1")
        mock_employment.objects.create.return_value = employment
        mock_assignment.objects.create.return_value = assignment

        envelope = build_teacher_envelope(
            source_tenant_id="source-tenant",
            target_tenant_id="target-tenant",
            canonical_data={},
        )
        result = apply_teacher_transfer_envelope(
            envelope,
            target_school_id="school-b",
            organization_id="org-1",
            user_id=99,
            allocation_fraction=Decimal("0.50"),
        )
        self.assertEqual(result.employment_id, "emp-1")
        self.assertEqual(result.assignment_id, "assign-1")
        mock_assignment.objects.create.assert_called_once()
        create_kwargs = mock_assignment.objects.create.call_args.kwargs
        self.assertEqual(create_kwargs["allocation_fraction"], Decimal("0.50"))

    @patch("apps.schools.models.School")
    def test_apply_rejects_org_mismatch(self, mock_school):
        school = SimpleNamespace(pk="school-b", organization_id="other-org", is_active=True)
        mock_school.objects.filter.return_value.first.return_value = school
        envelope = build_teacher_envelope(
            source_tenant_id="source-tenant",
            target_tenant_id="target-tenant",
            canonical_data={},
        )
        with self.assertRaises(TransferApplyError):
            apply_teacher_transfer_envelope(
                envelope,
                target_school_id="school-b",
                organization_id="org-1",
                user_id=1,
            )
