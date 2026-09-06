from decimal import Decimal

from django.test import TestCase, tag
from django.urls import reverse

from apps.accounts.models import User
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass


@tag("tenants_rls")
class TenantIdorGuardsTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.school_a = School.objects.create(
                name="Tenant A School",
                slug="tenant-a-school",
                subdomain="tenant-a-school",
                is_active=True,
            )
            self.school_b = School.objects.create(
                name="Tenant B School",
                slug="tenant-b-school",
                subdomain="tenant-b-school",
                is_active=True,
            )
            self.user_a = User.objects.create_user(
                username="tenant-admin-a",
                email="tenant-admin-a@example.com",
                password="x",
                role=User.Role.ADMIN,
            )
            SchoolMembership.objects.create(
                school=self.school_a,
                user=self.user_a,
                role=User.Role.ADMIN,
                is_primary=True,
            )

            self.profile = ComplianceProfile.objects.create(
                name="Default Finance",
                country_code="US",
                currency_code="USD",
                currency_symbol="$",
                is_active=True,
            )

            self.student_a = StudentProfile.objects.create(
                school=self.school_a,
                first_name="Alice",
                last_name="TenantA",
                student_code="A-STD-1",
            )
            self.student_b = StudentProfile.objects.create(
                school=self.school_b,
                first_name="Bob",
                last_name="TenantB",
                student_code="B-STD-1",
            )

            self.invoice_a = Invoice.objects.create(
                school=self.school_a,
                profile=self.profile,
                student=self.student_a,
                total_amount=Decimal("100.00"),
                balance_amount=Decimal("20.00"),
                status=Invoice.Status.PARTIAL,
            )
            self.invoice_b = Invoice.objects.create(
                school=self.school_b,
                profile=self.profile,
                student=self.student_b,
                total_amount=Decimal("500.00"),
                balance_amount=Decimal("100.00"),
                status=Invoice.Status.PARTIAL,
            )
            InvoiceLine.objects.create(
                invoice=self.invoice_a,
                description="Tuition A",
                quantity=Decimal("1.00"),
                unit_price=Decimal("100.00"),
                amount=Decimal("100.00"),
            )
            InvoiceLine.objects.create(
                invoice=self.invoice_b,
                description="Tuition B",
                quantity=Decimal("1.00"),
                unit_price=Decimal("500.00"),
                amount=Decimal("500.00"),
            )
            self.payment_a = Payment.objects.create(
                school=self.school_a,
                invoice=self.invoice_a,
                student=self.student_a,
                amount=Decimal("80.00"),
                method=PaymentMethodCode.CASH,
                status="completed",
            )
            self.payment_b = Payment.objects.create(
                school=self.school_b,
                invoice=self.invoice_b,
                student=self.student_b,
                amount=Decimal("400.00"),
                method=PaymentMethodCode.CASH,
                status="completed",
            )

    def _login_as_tenant_a(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        session["school_id"] = str(self.school_a.id)
        session.save()

    def test_student_detail_blocks_cross_tenant_idor(self):
        self._login_as_tenant_a()
        response = self.client.get(
            reverse("api:entity-student-detail", args=[self.student_b.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_invoice_detail_blocks_cross_tenant_idor(self):
        self._login_as_tenant_a()
        response = self.client.get(
            reverse("api:finance-invoice-detail", args=[self.invoice_b.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_payment_detail_blocks_cross_tenant_idor(self):
        self._login_as_tenant_a()
        response = self.client.get(
            reverse("api:finance-payment-detail", args=[self.payment_b.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_finance_analytics_is_school_scoped(self):
        self._login_as_tenant_a()
        response = self.client.get(reverse("api:finance-analytics"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # Money crosses this API as a Decimal rendered to a STRING, never as a
        # float -- apps/finance/json_decimal.py, and the scan_money_float gate
        # that forbids the float() round-trip. Comparing to 100.0 asserted the
        # JSON SPELLING rather than the value, so the test failed on correct
        # output. Compare as Decimal and the assertion survives either encoding.
        self.assertEqual(
            Decimal(str(payload.get("total_invoiced"))), Decimal("100.00")
        )
        self.assertEqual(
            Decimal(str(payload.get("total_collected"))), Decimal("80.00")
        )
        # What those numbers actually prove: school B's 500.00 invoice and
        # 400.00 payment are not in this tenant's totals. Stated so a future
        # reader cannot mistake the figures for arbitrary fixtures.
        self.assertEqual(self.invoice_b.total_amount, Decimal("500.00"))
        self.assertEqual(self.payment_b.amount, Decimal("400.00"))

    def test_finance_analytics_requires_school_context(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        if "school_id" in session:
            del session["school_id"]
        session.save()
        response = self.client.get(reverse("api:finance-analytics"))
        self.assertEqual(response.status_code, 400)

    def test_list_endpoints_without_school_context_do_not_leak_data(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        if "school_id" in session:
            del session["school_id"]
        session.save()

        students_response = self.client.get(reverse("api:entity-student-list"))
        invoices_response = self.client.get(reverse("api:finance-invoice-list"))
        payments_response = self.client.get(reverse("api:finance-payment-list"))

        self.assertEqual(students_response.status_code, 200)
        self.assertEqual(invoices_response.status_code, 200)
        self.assertEqual(payments_response.status_code, 200)

        students_payload = students_response.json()
        invoices_payload = invoices_response.json()
        payments_payload = payments_response.json()

        students_rows = (
            students_payload.get("results")
            if isinstance(students_payload, dict)
            else students_payload
        )
        invoices_rows = (
            invoices_payload.get("results")
            if isinstance(invoices_payload, dict)
            else invoices_payload
        )
        payments_rows = (
            payments_payload.get("results")
            if isinstance(payments_payload, dict)
            else payments_payload
        )

        self.assertEqual(len(students_rows or []), 0)
        self.assertEqual(len(invoices_rows or []), 0)
        self.assertEqual(len(payments_rows or []), 0)

    def test_payment_create_blocks_cross_tenant_invoice_reference(self):
        self._login_as_tenant_a()
        response = self.client.post(
            reverse("api:finance-payment-list"),
            data={
                "invoice": self.invoice_b.id,
                "amount": "10.00",
                "method": PaymentMethodCode.CASH,
            },
            content_type="application/json",
        )
        # The refusal can wear either of two shapes and both are correct: 403
        # from the permission layer, or 400 from the serializer, whose
        # school-scoped queryset makes a foreign invoice id simply not a valid
        # choice -- a ModelChoiceField's queryset IS its validator. Asserting
        # 403 alone failed on a platform that was refusing properly.
        self.assertIn(
            response.status_code,
            (400, 403, 404),
            f"a cross-tenant invoice reference must be refused, got "
            f"{response.status_code}",
        )
        # The status code is the weaker half. This is the assertion that
        # matters, and the test did not make it: whatever the shape of the
        # refusal, no payment may exist against another school's invoice
        # beyond the one its own school made.
        with rls_bypass():
            self.assertEqual(
                list(
                    Payment.objects.filter(invoice=self.invoice_b).values_list(
                        "id", flat=True
                    )
                ),
                [self.payment_b.id],
                "a payment landed against school B's invoice",
            )
