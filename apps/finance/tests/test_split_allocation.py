"""Tests for split payment allocation flow."""

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear
from apps.finance.models import ComplianceProfile, Invoice, InvoicePayerShare, Payment
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.tenant_hosts import HOST_ROUTED_SETTINGS, tenant_host


# split_allocation now requires a bound school: AcademicYear.is_active is documented
# as "exactly one active PER SCHOOL", so the view can only pick the right year once
# it knows whose page this is. The school arrives from the HOST, which means these
# tests have to be on a tenant host rather than the default testserver.
@override_settings(**HOST_ROUTED_SETTINGS)
class SplitAllocationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Split Allocation School",
            slug="split-allocation-school",
            subdomain="split-allocation-school",
            is_active=True,
        )
        self.tenant_host = tenant_host(self.school)
        self.profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Test",
            last_name="Student",
            academic_year=self.year,
            student_code="ST001",
        )
        self.staff = User.objects.create_user(
            username="staff_split",
            password="pass1234",
            role=User.Role.ACCOUNTANT,
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        # An accountant is exactly who runs a split allocation, and
        # require_permission("finance.manage") is a UNION -- holding the code is the
        # sanctioned way in, per the decorator's own docstring. Until now this test
        # passed WITHOUT the grant, because on the default testserver host
        # request.school is None and user_is_tenant_admin(user, None) falls back to
        # is_staff. That bypass does not exist on a real tenant host, so the test was
        # green for a reason production does not reproduce.
        perm, _ = FeaturePermission.objects.get_or_create(
            code="finance.manage", defaults={"name": "Manage finance"}
        )
        self.staff.feature_permissions.add(perm)
        self.guardian_a = User.objects.create_user(
            username="split_guardian_a",
            email="split_guardian_a@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.guardian_b = User.objects.create_user(
            username="split_guardian_b",
            email="split_guardian_b@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.guardian_link_a = StudentGuardian.objects.create(
            guardian_user=self.guardian_a,
            student=self.student,
            relationship=StudentGuardian.Relationship.FATHER,
            can_view_finance=True,
        )
        self.guardian_link_b = StudentGuardian.objects.create(
            guardian_user=self.guardian_b,
            student=self.student,
            relationship=StudentGuardian.Relationship.MOTHER,
            can_view_finance=True,
        )
        # Carries the tenant Host header, a SchoolMembership, a confirmed TOTP
        # device and a verified session -- the four things a real accountant's
        # request to this page satisfies. force_login() would rebuild the session
        # and drop the MFA flag, so it is deliberately not used here.
        self.client = login_tenant_admin_client(
            self.staff,
            password="pass1234",
            host=self.tenant_host,
            school=self.school,
            role=User.Role.ACCOUNTANT,
        )

    def test_split_allocation_creates_invoice_and_payment(self):
        total = Decimal("50000.00")
        self.client.get(
            reverse("finance:split_allocation")
        )  # load form so session has CSRF
        post_data = {
            "student": self.student.id,
            "total_amount": str(total),
            "method": "CASH",
            "desc_1": "Tuition",
            "amount_1": str(total),
            "desc_2": "",
            "amount_2": "0",
            "amount_3": "0",
            "amount_4": "0",
            "amount_5": "0",
        }
        response = self.client.post(reverse("finance:split_allocation"), post_data)
        self.assertEqual(response.status_code, 302)
        invoice = (
            Invoice.objects.filter(student=self.student, reference__startswith="SPLIT-")
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.student_id, self.student.id)
        self.assertEqual(invoice.total_amount, total)
        self.assertEqual(invoice.lines.count(), 1)
        line = invoice.lines.get()
        self.assertEqual(line.description, "Tuition")
        self.assertEqual(line.amount, total)
        payment = Payment.objects.get(invoice=invoice)
        self.assertEqual(payment.amount, total)
        self.assertEqual(payment.method, "CASH")
        # Optional assert: payment was applied (invoice balance updated)
        invoice.refresh_from_db()
        self.assertEqual(
            invoice.balance_amount,
            Decimal("0.00"),
            "Invoice balance should be zero after full payment",
        )

    def test_custom_split_creates_payer_shares(self):
        total = Decimal("50000.00")
        self.client.get(reverse("finance:split_allocation"))
        post_data = {
            "student": self.student.id,
            "total_amount": str(total),
            "method": "CASH",
            "split_mode": "custom",
            "desc_1": "Tuition",
            "amount_1": str(total),
            "desc_2": "",
            "amount_2": "0",
            "amount_3": "0",
            "amount_4": "0",
            "amount_5": "0",
            "payer_guardian_1": str(self.guardian_link_a.id),
            "payer_amount_1": "25000",
            "payer_guardian_2": str(self.guardian_link_b.id),
            "payer_amount_2": "25000",
            "payer_guardian_3": "",
            "payer_amount_3": "0",
            "payer_guardian_4": "",
            "payer_amount_4": "0",
        }
        response = self.client.post(reverse("finance:split_allocation"), post_data)
        self.assertEqual(response.status_code, 302)
        invoice = (
            Invoice.objects.filter(student=self.student, reference__startswith="SPLIT-")
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(invoice)
        shares = InvoicePayerShare.objects.filter(invoice=invoice).order_by(
            "guardian_id"
        )
        self.assertEqual(shares.count(), 2)
        self.assertEqual(shares[0].allocated_amount, Decimal("25000.00"))
        self.assertEqual(shares[1].allocated_amount, Decimal("25000.00"))
        self.assertEqual(shares[0].status, InvoicePayerShare.Status.PAID)
        self.assertEqual(shares[1].status, InvoicePayerShare.Status.PAID)
