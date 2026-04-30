import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import (
    BillingAccount,
    PlatformBillingProcessorConfig,
    BillingProcessorSyncEvent,
    PlatformLedgerEntry,
    Quote,
    RevenueSharePayout,
    TenantSubscription,
    UsageMeter,
)
from apps.billing.services import (
    execute_revenue_share_payout,
    apply_processor_snapshot,
    convert_quote_to_subscription,
    ensure_subscription_for_school,
    record_platform_charge,
    run_revenue_share_payout_execution,
    run_platform_billing_lifecycle,
    schedule_revenue_share_payout,
)
from apps.observability.models import PlatformIncident
from apps.schools.models import School
from apps.siteconfig.models import Plan


class PlatformBillingServicesTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Platform Growth",
            slug="platform-growth",
            base_price=Decimal("199.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Billing School",
            slug="billing-school",
            subdomain="billing-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.FREE_TRIAL,
        )

    def test_ensure_subscription_creates_platform_billing_records(self):
        account, subscription, created = ensure_subscription_for_school(self.school)

        self.assertTrue(created)
        self.assertEqual(account.status, BillingAccount.Status.TRIAL)
        self.assertEqual(subscription.status, TenantSubscription.Status.TRIALING)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.base_amount, Decimal("199.00"))
        self.assertEqual(subscription.billed_amount, Decimal("199.00"))

    def test_record_platform_charge_creates_ledger_entry(self):
        ensure_subscription_for_school(self.school)

        entry = record_platform_charge(
            school=self.school,
            amount="149.50",
            description="March platform subscription",
            reference="INV-PLATFORM-001",
            source="billing_dashboard",
        )

        self.assertEqual(entry.entry_type, PlatformLedgerEntry.EntryType.CHARGE)
        self.assertEqual(entry.amount, Decimal("149.50"))
        self.assertEqual(entry.reference, "INV-PLATFORM-001")

    def test_apply_processor_snapshot_updates_billing_objects_and_audits_event(self):
        event_time = timezone.now()

        event, account, subscription = apply_processor_snapshot(
            school=self.school,
            processor_code="stripe",
            event_type="invoice.payment_failed",
            account_status="past_due",
            subscription_status="past_due",
            external_customer_ref="cus_123",
            external_subscription_ref="sub_123",
            currency_code="EUR",
            billed_amount="249.00",
            current_period_start=event_time - timedelta(days=30),
            current_period_end=event_time + timedelta(days=2),
            happened_at=event_time,
            payload={"id": "evt_123"},
            message="Card declined",
        )

        self.assertEqual(event.status, BillingProcessorSyncEvent.Status.APPLIED)
        self.assertEqual(account.processor_code, "stripe")
        self.assertEqual(account.external_customer_ref, "cus_123")
        self.assertEqual(account.currency_code, "EUR")
        self.assertEqual(subscription.external_subscription_ref, "sub_123")
        self.assertEqual(subscription.status, TenantSubscription.Status.PAST_DUE)
        self.assertEqual(subscription.billed_amount, Decimal("249.00"))
        self.assertEqual(BillingProcessorSyncEvent.objects.count(), 1)

    def test_apply_processor_snapshot_invoice_paid_records_payment_usage_meter(self):
        """Paid webhook path creates ledger row once and bumps payment rail UsageMeter."""
        from apps.marketplace.monetization import USAGE_METRIC_PAYMENTS

        event_time = timezone.now()
        apply_processor_snapshot(
            school=self.school,
            processor_code="stripe",
            event_type="invoice.paid",
            account_status="active",
            subscription_status="active",
            external_customer_ref="cus_pay_use",
            external_subscription_ref="sub_pay_use",
            currency_code="USD",
            billed_amount="42.00",
            current_period_start=event_time - timedelta(days=30),
            current_period_end=event_time + timedelta(days=2),
            happened_at=event_time,
            payload={"id": "evt_pay_meter_unique"},
            processor_source_ref="evt_pay_meter_unique",
        )
        self.assertTrue(
            UsageMeter.objects.filter(
                school=self.school,
                metric_code=USAGE_METRIC_PAYMENTS,
            ).exists()
        )

    def test_run_platform_billing_lifecycle_converts_trial_and_generates_charge(self):
        self.school.trial_end_date = timezone.now().date() - timedelta(days=1)
        self.school.save(update_fields=["trial_end_date", "updated_at"])
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.current_period_start = timezone.now() - timedelta(days=31)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.billed_amount = Decimal("199.00")
        subscription.save(
            update_fields=[
                "current_period_start",
                "current_period_end",
                "billed_amount",
                "updated_at",
            ]
        )

        summary = run_platform_billing_lifecycle(
            as_of=timezone.now(), grace_days=7, suspension_days=30
        )

        subscription.refresh_from_db()
        account.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(summary["trial_converted"], 1)
        self.assertEqual(summary["charges_created"], 1)
        self.assertEqual(summary["renewed"], 1)
        self.assertEqual(self.school.billing_type, School.BillingType.REGULAR)
        self.assertEqual(subscription.status, TenantSubscription.Status.ACTIVE)
        self.assertEqual(account.status, BillingAccount.Status.ACTIVE)
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                billing_account=account,
                source="billing_lifecycle",
                entry_type=PlatformLedgerEntry.EntryType.CHARGE,
            ).exists()
        )

    def test_run_platform_billing_lifecycle_marks_overdue_subscriptions_suspended(self):
        self.school.billing_type = School.BillingType.REGULAR
        self.school.save(update_fields=["billing_type", "updated_at"])
        account, subscription, _ = ensure_subscription_for_school(self.school)
        anchor = timezone.now() - timedelta(days=45)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.current_period_start = anchor
        subscription.current_period_end = anchor + timedelta(days=1)
        subscription.billed_amount = Decimal("199.00")
        subscription.save(
            update_fields=[
                "status",
                "current_period_start",
                "current_period_end",
                "billed_amount",
                "updated_at",
            ]
        )

        summary = run_platform_billing_lifecycle(
            as_of=timezone.now(), grace_days=7, suspension_days=30
        )

        subscription.refresh_from_db()
        account.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(summary["suspended"], 1)
        self.assertEqual(subscription.status, TenantSubscription.Status.SUSPENDED)
        self.assertEqual(account.status, BillingAccount.Status.SUSPENDED)
        self.assertTrue(self.school.is_frozen)
        self.assertEqual(self.school.frozen_reason, "BILLING")

    def test_run_platform_billing_lifecycle_restores_paid_subscription(self):
        self.school.billing_type = School.BillingType.REGULAR
        self.school.is_frozen = True
        self.school.frozen_reason = "BILLING"
        self.school.save(
            update_fields=["billing_type", "is_frozen", "frozen_reason", "updated_at"]
        )
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.SUSPENDED
        subscription.current_period_end = timezone.now() + timedelta(days=10)
        subscription.save(update_fields=["status", "current_period_end", "updated_at"])
        account.status = BillingAccount.Status.SUSPENDED
        account.delinquent_since = timezone.now() - timedelta(days=12)
        account.save(update_fields=["status", "delinquent_since", "updated_at"])
        record_platform_charge(
            school=self.school,
            amount="199.00",
            reference="INV-RESTORE-001",
            source="billing_dashboard",
        )
        record_platform_charge(
            school=self.school,
            amount="199.00",
            entry_type=PlatformLedgerEntry.EntryType.CREDIT,
            reference="CR-RESTORE-001",
            source="payments",
        )

        summary = run_platform_billing_lifecycle(
            as_of=timezone.now(), grace_days=7, suspension_days=30
        )

        subscription.refresh_from_db()
        account.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(summary["restored"], 1)
        self.assertEqual(subscription.status, TenantSubscription.Status.ACTIVE)
        self.assertEqual(account.status, BillingAccount.Status.ACTIVE)
        self.assertIsNone(account.delinquent_since)
        self.assertFalse(self.school.is_frozen)
        self.assertEqual(self.school.frozen_reason, "")

    def test_convert_quote_to_subscription_creates_live_contract(self):
        quote = Quote.objects.create(
            school=self.school,
            plan=self.plan,
            status=Quote.Status.SENT,
            amount=Decimal("249.00"),
            currency_code="EUR",
            metadata={"billing_cycle": TenantSubscription.BillingCycle.ANNUAL},
        )

        success, message = convert_quote_to_subscription(quote.pk)

        self.assertTrue(success, message)
        quote.refresh_from_db()
        self.school.refresh_from_db()
        account = BillingAccount.objects.get(school=self.school)
        subscription = TenantSubscription.objects.get(school=self.school)
        self.assertEqual(quote.status, Quote.Status.ACCEPTED)
        self.assertEqual(self.school.billing_type, School.BillingType.REGULAR)
        self.assertEqual(account.status, BillingAccount.Status.ACTIVE)
        self.assertEqual(account.currency_code, "EUR")
        self.assertEqual(subscription.status, TenantSubscription.Status.ACTIVE)
        self.assertEqual(
            subscription.billing_cycle, TenantSubscription.BillingCycle.ANNUAL
        )
        self.assertEqual(subscription.base_amount, Decimal("249.00"))

    def test_schedule_revenue_share_payout_creates_scheduled_payout(self):
        payout = schedule_revenue_share_payout(
            payee_name="Verified Publisher",
            payee_ref="pub_001",
            payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER,
            processor_code="stripe_connect",
            gross_amount="400.00",
            fee_amount="40.00",
            currency_code="USD",
            source_school=self.school,
        )

        self.assertEqual(payout.status, RevenueSharePayout.Status.SCHEDULED)
        self.assertEqual(payout.net_amount, Decimal("360.00"))
        self.assertEqual(payout.processor_code, "stripe_connect")

    def test_execute_revenue_share_payout_updates_status_and_records_sync_event(self):
        PlatformBillingProcessorConfig.objects.create(
            code="relay",
            display_name="Relay",
            is_active=True,
            metadata={"payout_endpoint_url": "https://relay.example.org/payouts"},
        )
        payout = schedule_revenue_share_payout(
            payee_name="Verified Publisher",
            payee_ref="pub_001",
            processor_code="relay",
            gross_amount="400.00",
            fee_amount="40.00",
            currency_code="USD",
            source_school=self.school,
        )

        payout, result = execute_revenue_share_payout(
            payout,
            http_post_json=lambda url, payload, headers, timeout: (
                202,
                {"id": "relay_payout_001", "status": "submitted", "message": "queued"},
                "queued",
            ),
        )

        self.assertEqual(result["status"], "submitted")
        self.assertEqual(payout.status, RevenueSharePayout.Status.IN_TRANSIT)
        self.assertEqual(payout.external_payout_ref, "relay_payout_001")
        self.assertTrue(
            BillingProcessorSyncEvent.objects.filter(
                processor_code="relay",
                event_type="payout.executed",
                status=BillingProcessorSyncEvent.Status.APPLIED,
            ).exists()
        )

    def test_execute_revenue_share_payout_failure_creates_platform_incident(self):
        payout = schedule_revenue_share_payout(
            payee_name="Broken Publisher",
            payee_ref="pub_missing",
            processor_code="missing",
            gross_amount="80.00",
            fee_amount="5.00",
            currency_code="USD",
            source_school=self.school,
        )

        payout, result = execute_revenue_share_payout(payout)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(payout.status, RevenueSharePayout.Status.FAILED)
        incident = PlatformIncident.objects.get(
            source_system="billing.revenue_share",
            incident_type=PlatformIncident.IncidentType.BILLING,
            affected_school=self.school,
        )
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)
        self.assertIn("failed", incident.title.lower())

    def test_run_revenue_share_payout_execution_processes_due_records(self):
        PlatformBillingProcessorConfig.objects.create(
            code="relay",
            display_name="Relay",
            is_active=True,
            metadata={"payout_endpoint_url": "https://relay.example.org/payouts"},
        )
        schedule_revenue_share_payout(
            payee_name="Verified Publisher",
            payee_ref="pub_002",
            processor_code="relay",
            gross_amount="120.00",
            fee_amount="20.00",
            currency_code="USD",
            source_school=self.school,
        )

        summary = run_revenue_share_payout_execution(
            as_of=timezone.now(),
            http_post_json=lambda url, payload, headers, timeout: (
                200,
                {"id": "relay_payout_002", "status": "completed"},
                "ok",
            ),
        )

        self.assertEqual(summary["selected"], 1)
        self.assertEqual(summary["paid"], 1)
        self.assertEqual(
            RevenueSharePayout.objects.get(payee_ref="pub_002").status,
            RevenueSharePayout.Status.PAID,
        )

    def test_stripe_connect_processor_executes_transfer_api(self):
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={
                "api_key": "sk_test_123",
                "api_base_url": "https://api.stripe.com",
            },
        )
        payout = schedule_revenue_share_payout(
            payee_name="Stripe Publisher",
            payee_ref="acct_123",
            processor_code="stripe",
            gross_amount="250.00",
            fee_amount="25.00",
            currency_code="USD",
            source_school=self.school,
        )

        with patch(
            "apps.billing.processors._default_form_post",
            return_value=(
                200,
                {"id": "tr_123", "object": "transfer"},
                '{"id":"tr_123"}',
            ),
        ) as mock_post:
            payout, _result = execute_revenue_share_payout(payout)

        self.assertEqual(payout.status, RevenueSharePayout.Status.IN_TRANSIT)
        self.assertEqual(payout.external_payout_ref, "tr_123")
        called_url, called_payload, called_headers, called_timeout = (
            mock_post.call_args[0]
        )
        self.assertEqual(called_url, "https://api.stripe.com/v1/transfers")
        self.assertEqual(called_payload["destination"], "acct_123")
        self.assertEqual(called_payload["amount"], "22500")
        self.assertEqual(called_headers["Authorization"], "Bearer sk_test_123")
        self.assertEqual(called_timeout, 30)


class PlatformBillingCommandTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Platform Command Plan",
            slug="platform-command-plan",
            base_price=Decimal("249.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Command Billing School",
            slug="command-billing-school",
            subdomain="command-billing-school",
            is_active=True,
            plan=self.plan,
        )

    def workspace_tempdir(self):
        """Use system temp dir so we don't leave artifacts in the repo."""
        tmp = Path(tempfile.mkdtemp(prefix="billing_commands_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return tmp

    def test_import_platform_billing_snapshot_command_applies_snapshot(self):
        tmpdir = self.workspace_tempdir()
        payload = [
            {
                "school_slug": self.school.slug,
                "processor_code": "stripe",
                "event_type": "customer.subscription.updated",
                "account_status": "active",
                "subscription_status": "active",
                "external_customer_ref": "cus_command",
                "external_subscription_ref": "sub_command",
                "billed_amount": "249.00",
                "currency_code": "USD",
                "current_period_start": timezone.now().isoformat(),
                "current_period_end": (timezone.now() + timedelta(days=30)).isoformat(),
                "happened_at": timezone.now().isoformat(),
            }
        ]
        file_path = tmpdir / "billing_snapshot.json"
        file_path.write_text(json.dumps(payload), encoding="utf-8")

        call_command("import_platform_billing_snapshot", "--file", str(file_path))

        account = BillingAccount.objects.get(school=self.school)
        subscription = TenantSubscription.objects.get(school=self.school)
        self.assertEqual(account.external_customer_ref, "cus_command")
        self.assertEqual(subscription.external_subscription_ref, "sub_command")
        self.assertEqual(BillingProcessorSyncEvent.objects.count(), 1)

    def test_run_platform_billing_lifecycle_command_executes(self):
        ensure_subscription_for_school(self.school)

        call_command("run_platform_billing_lifecycle")

        self.assertTrue(TenantSubscription.objects.filter(school=self.school).exists())

    def test_run_revenue_share_payouts_command_executes_due_payouts(self):
        PlatformBillingProcessorConfig.objects.create(
            code="relay",
            display_name="Relay",
            is_active=True,
            metadata={"payout_endpoint_url": "https://relay.example.org/payouts"},
        )
        schedule_revenue_share_payout(
            payee_name="Command Publisher",
            payee_ref="pub-command",
            processor_code="relay",
            gross_amount="75.00",
            fee_amount="5.00",
            source_school=self.school,
        )

        with patch(
            "apps.billing.processors._default_json_post",
            return_value=(
                202,
                {"id": "relay_cmd_001", "status": "submitted"},
                "queued",
            ),
        ):
            call_command("run_revenue_share_payouts")

        payout = RevenueSharePayout.objects.get(payee_ref="pub-command")
        self.assertEqual(payout.status, RevenueSharePayout.Status.IN_TRANSIT)


class PlatformBillingDashboardTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Enterprise",
            slug="enterprise",
            base_price=Decimal("499.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Dashboard Billing School",
            slug="dashboard-billing-school",
            subdomain="dashboard-billing-school",
            is_active=True,
            plan=self.plan,
        )
        ensure_subscription_for_school(self.school)
        record_platform_charge(
            school=self.school,
            amount="499.00",
            description="First platform invoice",
            reference="INV-ENTERPRISE-001",
        )
        schedule_revenue_share_payout(
            payee_name="Publisher Zero",
            payee_ref="pub-zero",
            processor_code="stripe_connect",
            gross_amount="75.00",
            fee_amount="5.00",
            source_school=self.school,
        )
        apply_processor_snapshot(
            school=self.school,
            processor_code="stripe",
            event_type="invoice.paid",
            account_status="active",
            subscription_status="active",
            external_customer_ref="cus_dash",
            external_subscription_ref="sub_dash",
            billed_amount="499.00",
            current_period_start=timezone.now() - timedelta(days=5),
            current_period_end=timezone.now() + timedelta(days=25),
            happened_at=timezone.now(),
        )
        self.superuser = User.objects.create_user(
            username="billing-super",
            password="testpass123",
            is_superuser=True,
            is_staff=True,
        )

    def test_super_billing_dashboard_renders_platform_sections(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("super:billing_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform billing")
        self.assertContains(response, "Dashboard Billing School")
        self.assertContains(response, "Recent platform ledger")
        self.assertContains(response, "Processor sync ledger")
        self.assertContains(response, "Scheduled revenue-share payouts")
