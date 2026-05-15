"""Tests for the BankAccount dual-authorization workflow."""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.bank_account_dual_auth import (
    approve_bank_account_change,
    expire_stale_requests,
    reject_bank_account_change,
    request_bank_account_change,
)
from apps.finance.models import BankAccount
from apps.finance.models_dual_auth import BankAccountChangeRequest
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class BankAccountDualAuthTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
            },
        )
        self.school = School.objects.create(
            slug="test-school-dual-auth",
            name="Test School",
            subdomain="test-school-dual-auth",
        )
        self.requester = User.objects.create(
            username="alice@example.com",
            email="alice@example.com",
            role="ADMIN",
        )
        self.approver = User.objects.create(
            username="bob@example.com",
            email="bob@example.com",
            role="ADMIN",
        )
        self.account = BankAccount.objects.create(
            name="Main School Account",
            account_type=BankAccount.AccountType.BANK,
            account_number="123456789",
            bank_name="ABC Bank",
            branch="Main Branch",
            currency="XAF",
            region=self.region,
        )

    # --- request_bank_account_change ----------------------------------------

    def test_request_creates_pending_state(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "999999999"},
            requester=self.requester,
            reason="Bank notified us of an account number rotation.",
            bank_account=self.account,
        )
        self.assertEqual(request.state, BankAccountChangeRequest.State.PENDING)
        self.assertEqual(request.requester, self.requester)
        self.assertIsNone(request.approver)
        self.assertGreater(request.expires_at, timezone.now())
        # Live account is unchanged.
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "123456789")

    def test_short_reason_rejected(self):
        with self.assertRaises(ValidationError):
            request_bank_account_change(
                school=self.school,
                change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
                payload={"account_number": "999999999"},
                requester=self.requester,
                reason="hi",
                bank_account=self.account,
            )

    def test_create_with_target_account_rejected(self):
        with self.assertRaises(ValidationError):
            request_bank_account_change(
                school=self.school,
                change_kind=BankAccountChangeRequest.ChangeKind.CREATE,
                payload={"name": "Whatever"},
                requester=self.requester,
                reason="should not allow target with create",
                bank_account=self.account,
            )

    def test_update_without_target_account_rejected(self):
        with self.assertRaises(ValidationError):
            request_bank_account_change(
                school=self.school,
                change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
                payload={"account_number": "x"},
                requester=self.requester,
                reason="should not allow update without target",
            )

    def test_unknown_change_kind_rejected(self):
        with self.assertRaises(ValidationError):
            request_bank_account_change(
                school=self.school,
                change_kind="STEAL",
                payload={},
                requester=self.requester,
                reason="should not be possible",
                bank_account=self.account,
            )

    # --- approve_bank_account_change ----------------------------------------

    def test_approve_applies_update_atomically(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "999999999", "branch": "New Branch"},
            requester=self.requester,
            reason="Account rotation per bank notification.",
            bank_account=self.account,
        )
        approve_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="Verified with bank by phone callback.",
        )
        request.refresh_from_db()
        self.assertEqual(request.state, BankAccountChangeRequest.State.APPROVED)
        self.assertEqual(request.approver, self.approver)
        self.assertIsNotNone(request.decided_at)
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "999999999")
        self.assertEqual(self.account.branch, "New Branch")

    def test_approve_by_same_actor_rejected(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "999999999"},
            requester=self.requester,
            reason="Rotation per bank notification.",
            bank_account=self.account,
        )
        with self.assertRaises(ValidationError):
            approve_bank_account_change(
                request_id=request.id,
                approver=self.requester,  # same actor = rejected
                note="Trying to self-approve",
            )
        # Live account is unchanged.
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "123456789")

    def test_approve_creates_audit_log(self):
        from apps.compliance.models_audit import AuditLog

        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "999999999"},
            requester=self.requester,
            reason="Rotation per bank notification.",
            bank_account=self.account,
        )
        approve_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="Verified by callback.",
        )
        log = AuditLog.objects.filter(
            model_name="BankAccountChangeRequest", object_id=str(request.id)
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, "APPROVE")
        self.assertEqual(log.user, self.approver)
        self.assertEqual(log.sensitivity, AuditLog.Sensitivity.CRITICAL)
        self.assertEqual(log.old_values["account_number"], "123456789")
        self.assertEqual(log.new_values["account_number"], "999999999")

    def test_approve_create_kind_creates_account(self):
        starting = BankAccount.objects.count()
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.CREATE,
            payload={
                "name": "New Account",
                "account_type": BankAccount.AccountType.MTN_MOMO,
                "account_number": "678123456",
                "bank_name": "MTN Mobile Money",
                "currency": "XAF",
                "region_id": self.region.pk,
            },
            requester=self.requester,
            reason="Adding MoMo account for parent payments.",
        )
        approve_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="Approved.",
        )
        self.assertEqual(BankAccount.objects.count(), starting + 1)
        request.refresh_from_db()
        self.assertIsNotNone(request.bank_account)

    def test_approve_deactivate_kind_marks_inactive(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.DEACTIVATE,
            payload={},
            requester=self.requester,
            reason="Account closed by bank; deactivating.",
            bank_account=self.account,
        )
        approve_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="Confirmed with bank.",
        )
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)

    # --- reject_bank_account_change -----------------------------------------

    def test_reject_keeps_account_unchanged(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "FRAUD-999"},
            requester=self.requester,
            reason="Suspicious requester pattern; should be rejected.",
            bank_account=self.account,
        )
        reject_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="Could not verify with bank; declining.",
        )
        request.refresh_from_db()
        self.assertEqual(request.state, BankAccountChangeRequest.State.REJECTED)
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "123456789")

    def test_reject_by_same_actor_rejected(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "x"},
            requester=self.requester,
            reason="some reason that is long enough",
            bank_account=self.account,
        )
        with self.assertRaises(ValidationError):
            reject_bank_account_change(
                request_id=request.id,
                approver=self.requester,
                note="self-reject attempt",
            )

    # --- expire_stale_requests ----------------------------------------------

    def test_expire_sweeper_marks_old_requests(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "x"},
            requester=self.requester,
            reason="some valid reason text",
            bank_account=self.account,
        )
        # Force the request into the past.
        BankAccountChangeRequest.objects.filter(pk=request.pk).update(
            expires_at=timezone.now() - timedelta(hours=1)
        )
        n = expire_stale_requests()
        self.assertEqual(n, 1)
        request.refresh_from_db()
        self.assertEqual(request.state, BankAccountChangeRequest.State.EXPIRED)

    def test_expired_request_cannot_be_approved(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "x"},
            requester=self.requester,
            reason="some valid reason text",
            bank_account=self.account,
        )
        BankAccountChangeRequest.objects.filter(pk=request.pk).update(
            expires_at=timezone.now() - timedelta(hours=1)
        )
        with self.assertRaises(ValidationError):
            approve_bank_account_change(
                request_id=request.id,
                approver=self.approver,
                note="trying to approve an expired one",
            )

    def test_double_approve_rejected(self):
        request = request_bank_account_change(
            school=self.school,
            change_kind=BankAccountChangeRequest.ChangeKind.UPDATE,
            payload={"account_number": "999999999"},
            requester=self.requester,
            reason="some valid reason text",
            bank_account=self.account,
        )
        approve_bank_account_change(
            request_id=request.id,
            approver=self.approver,
            note="first approval",
        )
        with self.assertRaises(ValidationError):
            approve_bank_account_change(
                request_id=request.id,
                approver=self.approver,
                note="second approval (should fail)",
            )
