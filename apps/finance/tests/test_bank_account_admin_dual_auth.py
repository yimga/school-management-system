"""Tests for the BankAccountAdmin dual-authorization wire-up (v2.63).

Verifies that direct admin edits to BankAccount are converted into PENDING
BankAccountChangeRequest rows when BANK_ACCOUNT_CHANGES_REQUIRE_DUAL_AUTH
is True (the default), and pass through directly when False.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.finance.admin import BankAccountAdmin
from apps.finance.models import BankAccount
from apps.finance.models_dual_auth import BankAccountChangeRequest
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class BankAccountAdminDualAuthTests(TestCase):
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
            slug="test-admin-dual-auth",
            name="Test School Admin",
            subdomain="test-admin-dual-auth",
        )
        self.requester = User.objects.create(
            username="alice@example.com",
            email="alice@example.com",
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
        self.admin_instance = BankAccountAdmin(BankAccount, admin_site=MagicMock())

    def _build_request(self):
        request = MagicMock()
        request.user = self.requester
        request.school = self.school
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        return request

    def _build_form(self, *, changed_data, cleaned_data):
        form = MagicMock()
        form.changed_data = changed_data
        form.cleaned_data = cleaned_data
        return form

    # ---- Dual-auth ON (default) ------------------------------------------

    def test_update_files_pending_request_does_not_save(self):
        request = self._build_request()
        form = self._build_form(
            changed_data=["account_number"],
            cleaned_data={"account_number": "999999999", "notes": "Bank rotation per their notice."},
        )
        # The admin's `obj` in save_model is the form-bound instance — start
        # by simulating that the form already mutated the in-memory object,
        # which is the Django admin pattern.
        obj = BankAccount.objects.get(pk=self.account.pk)
        obj.account_number = "999999999"
        self.admin_instance.save_model(request, obj, form, change=True)
        # A pending request should now exist for this account.
        pending = BankAccountChangeRequest.objects.filter(
            bank_account=self.account, state=BankAccountChangeRequest.State.PENDING
        ).first()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.change_kind, BankAccountChangeRequest.ChangeKind.UPDATE)
        self.assertEqual(pending.payload.get("account_number"), "999999999")
        self.assertEqual(pending.requester, self.requester)
        self.assertEqual(pending.school, self.school)
        # Live row is still untouched.
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "123456789")

    def test_create_files_pending_request_does_not_save(self):
        request = self._build_request()
        form = self._build_form(
            changed_data=[],  # CREATE doesn't use changed_data
            cleaned_data={
                "name": "New MoMo Account",
                "account_type": BankAccount.AccountType.MTN_MOMO,
                "account_number": "678123456",
                "bank_name": "MTN Mobile Money",
                "branch": "",
                "currency": "XAF",
                "notes": "Adding for parent payments",
                # FK
                "region": self.region,
            },
        )
        obj = BankAccount(
            name="New MoMo Account",
            account_type=BankAccount.AccountType.MTN_MOMO,
            account_number="678123456",
            currency="XAF",
            region=self.region,
        )
        before = BankAccount.objects.count()
        self.admin_instance.save_model(request, obj, form, change=False)
        # Live BankAccount row count unchanged.
        self.assertEqual(BankAccount.objects.count(), before)
        # A pending CREATE request exists.
        pending = BankAccountChangeRequest.objects.filter(
            bank_account__isnull=True,
            change_kind=BankAccountChangeRequest.ChangeKind.CREATE,
            state=BankAccountChangeRequest.State.PENDING,
        ).first()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.payload.get("account_number"), "678123456")
        # FK serialized as region_id.
        self.assertEqual(pending.payload.get("region_id"), self.region.pk)

    def test_delete_files_deactivate_request(self):
        request = self._build_request()
        before_pending = BankAccountChangeRequest.objects.filter(
            change_kind=BankAccountChangeRequest.ChangeKind.DEACTIVATE
        ).count()
        self.admin_instance.delete_model(request, self.account)
        after_pending = BankAccountChangeRequest.objects.filter(
            change_kind=BankAccountChangeRequest.ChangeKind.DEACTIVATE
        ).count()
        self.assertEqual(after_pending, before_pending + 1)
        # Live account is still active until peer approves.
        self.account.refresh_from_db()
        self.assertTrue(self.account.is_active)

    # ---- Dual-auth OFF (operator escape hatch) ---------------------------

    @override_settings(BANK_ACCOUNT_CHANGES_REQUIRE_DUAL_AUTH=False)
    def test_dual_auth_off_saves_directly(self):
        request = self._build_request()
        form = self._build_form(
            changed_data=["branch"],
            cleaned_data={"branch": "New Branch"},
        )
        obj = BankAccount.objects.get(pk=self.account.pk)
        obj.branch = "New Branch"
        self.admin_instance.save_model(request, obj, form, change=True)
        self.account.refresh_from_db()
        self.assertEqual(self.account.branch, "New Branch")

    # ---- No-tenant guard --------------------------------------------------

    def test_no_tenant_context_refuses_to_file(self):
        request = self._build_request()
        request.school = None
        # Make the user.profile attribute also resolve to None to keep the
        # _resolve_school helper fall through.
        request.user = MagicMock(spec=User)
        request.user.is_authenticated = True
        request.user.school = None
        request.user.profile = None
        form = self._build_form(
            changed_data=["account_number"],
            cleaned_data={"account_number": "999999999"},
        )
        obj = BankAccount.objects.get(pk=self.account.pk)
        before = BankAccountChangeRequest.objects.count()
        self.admin_instance.save_model(request, obj, form, change=True)
        # No request filed.
        self.assertEqual(BankAccountChangeRequest.objects.count(), before)
        # Live account untouched.
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "123456789")
