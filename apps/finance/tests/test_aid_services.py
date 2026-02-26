from decimal import Decimal

from django.test import TestCase

from apps.finance.aid_services import execute_disbursement, get_endowment_health_report
from apps.finance.models import (
    AidAuditLog,
    AwardSource,
    ComplianceProfile,
    FinancialAidApplication,
    Invoice,
    InvoiceLine,
    JournalEntry,
    Scholarship,
    Payment,
)
from apps.finance.services import recalculate_invoice
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import SiteSettings, WebhookDelivery, WebhookSubscription


class AidDisbursementLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Aid Ledger School",
            slug="aid-ledger-school",
            subdomain="aid-ledger-school",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Default Finance Profile",
            country_code="US",
            currency_code="USD",
            is_active=True,
        )
        site = SiteSettings.get_solo()
        site.compliance_profile = self.profile
        site.save(update_fields=["compliance_profile", "updated_at"])

        self.student_with_invoice = StudentProfile.objects.create(
            school=self.school,
            first_name="Alan",
            last_name="Turing",
            custom_attributes={"gpa": 3.8},
        )
        self.student_without_invoice = StudentProfile.objects.create(
            school=self.school,
            first_name="Katherine",
            last_name="Johnson",
            custom_attributes={"gpa": 3.9},
        )
        self.source = AwardSource.objects.create(
            school=self.school,
            name="STEM Endowment",
            total_budget=Decimal("5000.00"),
            remaining_funds=Decimal("5000.00"),
            currency="USD",
        )
        self.scholarship = Scholarship.objects.create(
            school=self.school,
            source=self.source,
            title="STEM Merit",
            award_amount=Decimal("250.00"),
            eligibility_criteria={},
            is_active=True,
        )
        self.webhook = WebhookSubscription.objects.create(
            school=self.school,
            event_type="finance.aid_disbursed",
            target_url="https://example.org/finance-webhook",
            secret="aid-test-secret",
            is_active=True,
        )

    def _application(self, student: StudentProfile, amount: str) -> FinancialAidApplication:
        return FinancialAidApplication.objects.create(
            school=self.school,
            student=student,
            scholarship=self.scholarship,
            status=FinancialAidApplication.Status.APPROVED,
            amount_approved=Decimal(amount),
        )

    def test_disbursement_with_invoice_posts_balanced_ledger(self):
        invoice = Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            student=self.student_with_invoice,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            reference="INV-AID-1",
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        recalculate_invoice(invoice)

        app = self._application(self.student_with_invoice, "30.00")
        result = execute_disbursement(app.pk, school_id=self.school.pk)

        self.assertTrue(result["ok"])
        app.refresh_from_db()
        self.assertEqual(app.status, FinancialAidApplication.Status.DISBURSED)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("70.00"))
        self.assertEqual(invoice.balance_amount, Decimal("70.00"))
        self.assertTrue(AidAuditLog.objects.filter(application=app, action="disbursement").exists())

        entry = JournalEntry.objects.get(source_type="financial_aid_disbursement", source_id=app.pk)
        debit_total = sum((line.debit for line in entry.lines.all()), Decimal("0.00"))
        credit_total = sum((line.credit for line in entry.lines.all()), Decimal("0.00"))
        self.assertEqual(debit_total, Decimal("30.00"))
        self.assertEqual(credit_total, Decimal("30.00"))
        account_codes = {line.account.code for line in entry.lines.all()}
        self.assertIn("658", account_codes)
        self.assertIn("411", account_codes)
        delivery = WebhookDelivery.objects.get(subscription=self.webhook, event_id=f"aid-disbursed-{app.pk}")
        self.assertEqual(delivery.event_type, "finance.aid_disbursed")
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)

    def test_disbursement_without_invoice_creates_payment_and_ledger(self):
        app = self._application(self.student_without_invoice, "25.00")

        result = execute_disbursement(app.pk, school_id=self.school.pk)

        self.assertTrue(result["ok"])
        app.refresh_from_db()
        self.assertEqual(app.status, FinancialAidApplication.Status.DISBURSED)
        payment = Payment.objects.get(student=self.student_without_invoice, amount=Decimal("25.00"))
        self.assertEqual(payment.status, "completed")

        entry = JournalEntry.objects.get(source_type="financial_aid_disbursement", source_id=app.pk)
        debit_total = sum((line.debit for line in entry.lines.all()), Decimal("0.00"))
        credit_total = sum((line.credit for line in entry.lines.all()), Decimal("0.00"))
        self.assertEqual(debit_total, Decimal("25.00"))
        self.assertEqual(credit_total, Decimal("25.00"))

        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("4975.00"))
        delivery = WebhookDelivery.objects.get(subscription=self.webhook, event_id=f"aid-disbursed-{app.pk}")
        self.assertEqual(delivery.event_type, "finance.aid_disbursed")

    def test_endowment_report_includes_multi_year_projections(self):
        app = self._application(self.student_without_invoice, "25.00")
        result = execute_disbursement(app.pk, school_id=self.school.pk)
        self.assertTrue(result["ok"])

        report = get_endowment_health_report(self.school.pk, years_ahead=3)
        self.assertEqual(len(report), 1)
        row = report[0]
        self.assertIn("annual_burn_estimate", row)
        self.assertIn("projections", row)
        self.assertEqual(len(row["projections"]), 3)
        self.assertEqual(row["projections"][0]["year_offset"], 1)
