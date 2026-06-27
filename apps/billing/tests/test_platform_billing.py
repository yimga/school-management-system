import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import (
    BillingAccount,
    Entitlement,
    PlatformBillingProcessorConfig,
    BillingProcessorSyncEvent,
    PlatformInvoice,
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

    def test_ensure_subscription_applies_country_multiplier(self):
        from apps.billing.services import _resolve_country_multiplier_for_school
        from apps.siteconfig.models_platform_catalog import CountryMultiplier, RegionConfig

        region, _ = RegionConfig.objects.get_or_create(
            code="KEN",
            defaults={
                "name": "Kenya",
                "default_currency": "KES",
                "grading_scale": "0-100",
            },
        )
        CountryMultiplier.objects.update_or_create(
            country_code="KEN",
            defaults={"multiplier": Decimal("0.75"), "is_active": True},
        )
        self.school.default_region = region
        self.school.save(update_fields=["default_region"])

        self.assertEqual(_resolve_country_multiplier_for_school(self.school), Decimal("0.75"))

        _account, subscription, _created = ensure_subscription_for_school(self.school)

        self.assertEqual(subscription.country_multiplier, Decimal("0.75"))
        self.assertEqual(subscription.billed_amount, Decimal("149.25"))

    def test_ensure_subscription_materializes_entitlements_and_limits(self):
        from apps.billing.entitlements import can, limits

        self.plan.included_features = ["reports"]
        self.plan.max_students = 2
        self.plan.save(update_fields=["included_features", "max_students", "updated_at"])
        self.school.addons = ["analytics"]
        self.school.save(update_fields=["addons", "updated_at"])

        ensure_subscription_for_school(self.school)

        self.assertTrue(
            Entitlement.objects.filter(
                school=self.school,
                code="reports",
                kind=Entitlement.Kind.FEATURE,
                is_enabled=True,
            ).exists()
        )
        self.assertTrue(can(self.school, "reports"))
        self.assertTrue(can(self.school, "analytics"))
        self.assertEqual(limits(self.school)["max_students"]["limit_value"], 2)

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

    def test_convert_quote_honors_school_year_cycle(self):
        # Regression: the quote-acceptance path used to coerce any cycle outside
        # {MONTHLY, ANNUAL, MANUAL} to MONTHLY, so a SCHOOL_YEAR quote was silently
        # downgraded. It must now be stored verbatim and billed on a yearly period.
        quote = Quote.objects.create(
            school=self.school,
            plan=self.plan,
            status=Quote.Status.SENT,
            amount=Decimal("1800.00"),
            currency_code="USD",
            metadata={"billing_cycle": TenantSubscription.BillingCycle.SCHOOL_YEAR},
        )

        success, message = convert_quote_to_subscription(quote.pk)

        self.assertTrue(success, message)
        subscription = TenantSubscription.objects.get(school=self.school)
        self.assertEqual(
            subscription.billing_cycle,
            TenantSubscription.BillingCycle.SCHOOL_YEAR,
        )
        # Period spans ~one school year, not a month.
        self.assertIsNotNone(subscription.current_period_start)
        self.assertIsNotNone(subscription.current_period_end)
        span = subscription.current_period_end - subscription.current_period_start
        self.assertEqual(span, timedelta(days=365))

    def test_run_lifecycle_renews_school_year_subscription(self):
        # A SCHOOL_YEAR subscription past its period end must auto-renew (was
        # unbillable when _cycle_delta returned None for it) and advance the next
        # period by a full year.
        self.school.billing_type = School.BillingType.REGULAR
        self.school.save(update_fields=["billing_type", "updated_at"])
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.billing_cycle = TenantSubscription.BillingCycle.SCHOOL_YEAR
        period_end = timezone.now() - timedelta(days=1)
        subscription.current_period_start = period_end - timedelta(days=365)
        subscription.current_period_end = period_end
        subscription.billed_amount = Decimal("1800.00")
        subscription.save(
            update_fields=[
                "status",
                "billing_cycle",
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
        self.assertEqual(summary["renewed"], 1)
        self.assertEqual(summary["charges_created"], 1)
        # Next period end advanced by one school year from the old period end.
        self.assertEqual(
            subscription.current_period_end, period_end + timedelta(days=365)
        )

    def _set_country_tax(self, code, rate, behavior):
        from apps.billing.models import CountryBillingProfile
        from apps.siteconfig.models_platform_catalog import CountryMultiplier

        CountryMultiplier.objects.update_or_create(
            country_code=code,
            defaults={
                "multiplier": Decimal("1.0"),
                "tax_rate": Decimal(rate),
                "is_active": True,
            },
        )
        CountryBillingProfile.objects.update_or_create(
            country_code=code, defaults={"tax_behavior": behavior}
        )
        self.school.country_code = code
        self.school.save(update_fields=["country_code", "updated_at"])

    def test_resolve_charge_tax_exclusive_adds_tax(self):
        from apps.billing.models import CountryBillingProfile
        from apps.billing.services import resolve_charge_tax

        self._set_country_tax(
            "KE", "0.1600", CountryBillingProfile.TaxBehavior.EXCLUSIVE
        )
        tax = resolve_charge_tax(self.school, Decimal("100.00"))
        self.assertEqual(tax["tax_amount"], Decimal("16.00"))
        self.assertEqual(tax["tax_rate"], Decimal("0.1600"))

    def test_resolve_charge_tax_inclusive_adds_nothing(self):
        from apps.billing.models import CountryBillingProfile
        from apps.billing.services import resolve_charge_tax

        # Tax-inclusive markets must NOT get a separate tax line (it's in the price).
        self._set_country_tax(
            "KE", "0.1600", CountryBillingProfile.TaxBehavior.INCLUSIVE
        )
        tax = resolve_charge_tax(self.school, Decimal("100.00"))
        self.assertEqual(tax["tax_amount"], Decimal("0.00"))

    def test_resolve_charge_tax_zero_rate_adds_nothing(self):
        from apps.billing.models import CountryBillingProfile
        from apps.billing.services import resolve_charge_tax

        self._set_country_tax(
            "KE", "0.0000", CountryBillingProfile.TaxBehavior.EXCLUSIVE
        )
        tax = resolve_charge_tax(self.school, Decimal("100.00"))
        self.assertEqual(tax["tax_amount"], Decimal("0.00"))

    def test_run_lifecycle_adds_tax_line_for_exclusive_country(self):
        from apps.billing.models import CountryBillingProfile

        self.school.billing_type = School.BillingType.REGULAR
        self.school.save(update_fields=["billing_type", "updated_at"])
        self._set_country_tax(
            "KE", "0.1600", CountryBillingProfile.TaxBehavior.EXCLUSIVE
        )
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.current_period_start = timezone.now() - timedelta(days=31)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.billed_amount = Decimal("100.00")
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

        self.assertEqual(summary["renewed"], 1)
        self.assertEqual(summary["tax_charges_created"], 1)
        self.assertEqual(summary["tax_amount"], Decimal("16.00"))
        tax_entry = PlatformLedgerEntry.objects.filter(
            billing_account=account, source="billing_lifecycle_tax"
        ).first()
        self.assertIsNotNone(tax_entry)
        self.assertEqual(tax_entry.amount, Decimal("16.00"))
        self.assertEqual(tax_entry.entry_type, PlatformLedgerEntry.EntryType.CHARGE)

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


class CycleDeltaTests(SimpleTestCase):
    """Renewal-period math for every billing cycle (no DB)."""

    def test_recurring_cycle_durations(self):
        from apps.billing.services import _cycle_delta

        Cycle = TenantSubscription.BillingCycle
        self.assertEqual(_cycle_delta(Cycle.MONTHLY), timedelta(days=30))
        self.assertEqual(_cycle_delta(Cycle.SEMESTER), timedelta(days=182))
        self.assertEqual(_cycle_delta(Cycle.SCHOOL_YEAR), timedelta(days=365))
        self.assertEqual(_cycle_delta(Cycle.ANNUAL), timedelta(days=365))
        self.assertEqual(_cycle_delta(Cycle.MULTI_YEAR), timedelta(days=730))

    def test_manual_and_unknown_are_non_recurring(self):
        from apps.billing.services import _cycle_delta

        self.assertIsNone(_cycle_delta(TenantSubscription.BillingCycle.MANUAL))
        self.assertIsNone(_cycle_delta("WHATEVER"))
        self.assertIsNone(_cycle_delta(""))

    @override_settings(BILLING_CYCLE_DAYS_SCHOOL_YEAR=300)
    def test_duration_is_operator_overridable(self):
        from apps.billing.services import _cycle_delta

        self.assertEqual(
            _cycle_delta(TenantSubscription.BillingCycle.SCHOOL_YEAR),
            timedelta(days=300),
        )

    @override_settings(BILLING_CYCLE_DAYS_SEMESTER=0)
    def test_non_positive_override_is_non_recurring(self):
        from apps.billing.services import _cycle_delta

        self.assertIsNone(_cycle_delta(TenantSubscription.BillingCycle.SEMESTER))

    @override_settings(BILLING_CYCLE_DAYS_MULTI_YEAR="not-a-number")
    def test_invalid_override_falls_back_to_default(self):
        from apps.billing.services import _cycle_delta

        self.assertEqual(
            _cycle_delta(TenantSubscription.BillingCycle.MULTI_YEAR),
            timedelta(days=730),
        )


class PreviewPlanChangeTests(SimpleTestCase):
    """Mid-period proration math (no DB) — wires proration.compute_proration."""

    class _Sub:
        def __init__(self, start, end, amount):
            self.current_period_start = start
            self.current_period_end = end
            self.billed_amount = Decimal(amount)
            self.base_amount = Decimal(amount)
            self.addons_amount = Decimal("0.00")

    def test_midperiod_change_credits_unused_and_charges_new(self):
        from apps.billing.services import preview_plan_change

        now = timezone.now()
        sub = self._Sub(now - timedelta(days=15), now + timedelta(days=15), "100.00")
        p = preview_plan_change(sub, Decimal("200.00"), as_of=now)
        self.assertGreater(p["remaining_days"], 0)
        # Only part of the old plan is credited back (not the whole period).
        self.assertGreater(p["old_unused_credit"], Decimal("0.00"))
        self.assertLess(p["old_unused_credit"], Decimal("100.00"))
        # Net change equals new prorated charge minus old unused credit.
        self.assertEqual(
            p["net_change"], p["new_prorated_charge"] - p["old_unused_credit"]
        )
        # Upgrading (200 > 100) costs more for the remainder.
        self.assertGreater(p["net_change"], Decimal("0.00"))

    def test_no_active_period_zeroes_proration(self):
        from apps.billing.services import preview_plan_change

        now = timezone.now()
        # Period already ended -> nothing to prorate.
        sub = self._Sub(now - timedelta(days=40), now - timedelta(days=1), "100.00")
        p = preview_plan_change(sub, Decimal("200.00"), as_of=now)
        self.assertEqual(p["remaining_days"], 0)
        self.assertEqual(p["old_unused_credit"], Decimal("0.00"))
        self.assertEqual(p["new_prorated_charge"], Decimal("0.00"))
        self.assertEqual(p["net_change"], Decimal("0.00"))


class ChangeSubscriptionPlanTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Starter", slug="starter", base_price=Decimal("100.00"), is_active=True
        )
        self.plan2 = Plan.objects.create(
            name="Growth", slug="growth", base_price=Decimal("200.00"), is_active=True
        )
        self.school = School.objects.create(
            name="Change School",
            slug="change-school",
            subdomain="change-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )

    def test_change_plan_prorates_and_repoints(self):
        from apps.billing.services import change_subscription_plan

        account, subscription, _ = ensure_subscription_for_school(self.school)
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=15)
        subscription.current_period_end = now + timedelta(days=15)
        subscription.billed_amount = Decimal("100.00")
        subscription.save(
            update_fields=[
                "current_period_start",
                "current_period_end",
                "billed_amount",
                "updated_at",
            ]
        )

        summary = change_subscription_plan(
            self.school, self.plan2, new_amount=Decimal("200.00"), as_of=now
        )

        subscription.refresh_from_db()
        self.school.refresh_from_db()
        self.assertTrue(summary["changed"])
        self.assertEqual(subscription.plan, self.plan2)
        self.assertEqual(subscription.base_amount, Decimal("200.00"))
        self.assertEqual(self.school.plan, self.plan2)
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                billing_account=account, source="billing_plan_change_credit"
            ).exists()
        )
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                billing_account=account, source="billing_plan_change_charge"
            ).exists()
        )

    def test_change_to_same_plan_is_noop(self):
        from apps.billing.services import change_subscription_plan

        ensure_subscription_for_school(self.school)
        summary = change_subscription_plan(
            self.school, self.plan, new_amount=Decimal("100.00")
        )
        self.assertFalse(summary["changed"])


class RenewalReminderTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Reminder", slug="reminder", base_price=Decimal("100.00"), is_active=True
        )
        self.school = School.objects.create(
            name="Reminder School",
            slug="reminder-school",
            subdomain="reminder-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )

    def _arm_subscription(self, days_until=3):
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.current_period_end = timezone.now() + timedelta(days=days_until)
        subscription.save(update_fields=["status", "current_period_end", "updated_at"])
        return subscription

    @patch(
        "apps.platform_runtime.reactivation_engine._portal_url_for_reactivation",
        return_value="https://reminder-school.runmycampus.com/authentication/login/",
    )
    @patch(
        "apps.platform_runtime.reactivation_engine._resolve_admin_email",
        return_value="owner@example.com",
    )
    def test_reminder_publishes_once_then_dedups(self, _email, _url):
        from apps.billing.renewal_reminders import run_subscription_renewal_reminders
        from apps.platform_runtime.models import PlatformEventLog

        self._arm_subscription(days_until=3)

        first = run_subscription_renewal_reminders(warning_days=7)
        self.assertEqual(first["published"], 1)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="tenant.subscription.expiring_soon"
            ).exists()
        )

        # Second run within the same period must not re-publish (dedup).
        second = run_subscription_renewal_reminders(warning_days=7)
        self.assertEqual(second["published"], 0)
        self.assertEqual(second["skipped_deduped"], 1)

    @patch(
        "apps.platform_runtime.reactivation_engine._resolve_admin_email",
        return_value="owner@example.com",
    )
    def test_reminder_skips_subscription_outside_window(self, _email):
        from apps.billing.renewal_reminders import run_subscription_renewal_reminders

        self._arm_subscription(days_until=30)  # outside a 7-day window
        summary = run_subscription_renewal_reminders(warning_days=7)
        self.assertEqual(summary["published"], 0)

    @patch(
        "apps.platform_runtime.reactivation_engine._resolve_admin_email",
        return_value="",
    )
    def test_reminder_skips_when_no_admin_email(self, _email):
        from apps.billing.renewal_reminders import run_subscription_renewal_reminders

        self._arm_subscription(days_until=3)
        summary = run_subscription_renewal_reminders(warning_days=7)
        self.assertEqual(summary["published"], 0)
        self.assertEqual(summary["skipped_no_email"], 1)

    @patch(
        "apps.platform_runtime.reactivation_engine._portal_url_for_reactivation",
        return_value="https://reminder-school.runmycampus.com/authentication/login/",
    )
    @patch(
        "apps.platform_runtime.reactivation_engine._resolve_admin_email",
        return_value="owner@example.com",
    )
    def test_trial_ending_publishes_once_then_dedups(self, _email, _url):
        from apps.billing.renewal_reminders import run_trial_ending_reminders
        from apps.platform_runtime.models import PlatformEventLog

        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.TRIALING
        subscription.trial_end_date = (timezone.now() + timedelta(days=3)).date()
        subscription.save(
            update_fields=["status", "trial_end_date", "updated_at"]
        )

        first = run_trial_ending_reminders(warning_days=7)
        self.assertEqual(first["published"], 1)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="tenant.subscription.trial_ending"
            ).exists()
        )

        second = run_trial_ending_reminders(warning_days=7)
        self.assertEqual(second["published"], 0)
        self.assertEqual(second["skipped_deduped"], 1)


class PlatformInvoiceTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Invoice Plan",
            slug="invoice-plan",
            base_price=Decimal("100.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Invoice School",
            slug="invoice-school",
            subdomain="invoice-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )

    def test_issue_invoice_is_idempotent_and_gapless(self):
        from apps.billing.services import issue_platform_invoice

        account, _sub, _ = ensure_subscription_for_school(self.school)
        common = dict(
            school=self.school,
            billing_account=account,
            period_start=None,
            period_end=None,
            subtotal="100.00",
            discount_amount="0.00",
            tax_amount="16.00",
            total="116.00",
            currency_code="USD",
        )
        inv1 = issue_platform_invoice(reference_stem="STEM-A", **common)
        inv1_again = issue_platform_invoice(reference_stem="STEM-A", **common)
        self.assertEqual(inv1.pk, inv1_again.pk)  # idempotent on reference_stem
        inv2 = issue_platform_invoice(reference_stem="STEM-B", **common)
        self.assertEqual(inv2.sequence, inv1.sequence + 1)  # gapless
        self.assertTrue(inv1.number.startswith("INV-"))
        self.assertEqual(inv1.total, Decimal("116.00"))

    def test_run_lifecycle_issues_numbered_invoice(self):
        account, subscription, _ = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.current_period_start = timezone.now() - timedelta(days=31)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.billed_amount = Decimal("100.00")
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

        self.assertEqual(summary["invoices_issued"], 1)
        inv = PlatformInvoice.objects.filter(school=self.school).first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.subtotal, Decimal("100.00"))
        self.assertTrue(inv.number.startswith("INV-"))

    def test_backfill_issues_invoice_from_existing_ledger(self):
        from apps.billing.services import backfill_platform_invoices

        record_platform_charge(
            school=self.school,
            amount=Decimal("100.00"),
            description="Platform subscription renewal",
            reference="SUBP-1",
            source="billing_lifecycle",
            metadata={},
        )
        record_platform_charge(
            school=self.school,
            amount=Decimal("16.00"),
            description="Platform subscription tax",
            reference="SUBP-1-TAX",
            source="billing_lifecycle_tax",
        )

        summary = backfill_platform_invoices()

        self.assertGreaterEqual(summary["issued"], 1)
        inv = PlatformInvoice.objects.get(reference_stem="SUBP-1")
        self.assertEqual(inv.subtotal, Decimal("100.00"))
        self.assertEqual(inv.tax_amount, Decimal("16.00"))
        self.assertEqual(inv.total, Decimal("116.00"))
        # Idempotent: a second run issues nothing new.
        again = backfill_platform_invoices()
        self.assertEqual(again["issued"], 0)
