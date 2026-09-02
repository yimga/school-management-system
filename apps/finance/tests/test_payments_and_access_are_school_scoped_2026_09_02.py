"""Payments, the cash closure, and finance-access grants are bounded by school.

Three more sites carrying `# tenant-isolation-allow: scoped-via-surrounding-tenant-
context`, where no surrounding context bounded anything:

* ``payment_list`` -- ``Payment.objects.filter(invoice__profile=profile)``.
  ``ComplianceProfile`` has a ``country_code`` and no school column, so the page
  listed every co-located school's receipts.
* ``cash_office_closure`` -- the same profile-only bound on the query that computes
  ``cash_collected``. This page reconciles PHYSICAL cash against recorded takings, so
  another school's cash inflated the figure a bursar is held to, and the discrepancy
  it reports was wrong by that amount.
* ``request_finance_access`` -- ``StudentProfile.objects.filter(id=student_id)`` where
  ``student_id`` comes straight from ``request.POST``, and the block immediately after
  it sets ``can_view_finance=True`` on that student's guardians. That is a cross-tenant
  **write**: staff at one school could grant another school's guardians access to their
  own school's invoices.

Payments are scoped through the INVOICE's school rather than ``Payment.school``.
Both columns are nullable; migration ``0082_backfill_arrears_invoice_school``
backfilled ``Invoice.school`` for every AR row with a student, and nothing ever
backfilled ``Payment.school`` -- so keying on the payment's own column would have
hidden a school's legacy receipts from its own list.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.accounts.models import Permission as FeaturePermission, User
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    Payment,
    PaymentMethodCode,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School, SchoolMembership
from apps.test_utils.tenant_hosts import (
    HOST_ROUTED_SETTINGS,
    TENANT_URLCONF,
    assert_resolved_urlconf,
    tenant_client,
    tenant_host,
)


@override_settings(**HOST_ROUTED_SETTINGS)
class PaymentsAreSchoolScopedTests(TestCase):
    """Two schools sharing ONE ComplianceProfile -- i.e. the same country."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="CM", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.ours, self.our_payment = self._school_with_cash_payment("ours", "PAY-OURS")
        self.theirs, self.their_payment = self._school_with_cash_payment(
            "theirs", "PAY-THEIRS"
        )
        self.staff = User.objects.create_user(
            username="pay_staff", password="pass1234", role=User.Role.ACCOUNTANT
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        SchoolMembership.objects.get_or_create(
            user=self.staff,
            school=self.ours,
            defaults={"role": User.Role.ACCOUNTANT, "is_primary": True},
        )
        for code in ("finance.view", "finance.manage"):
            perm, _ = FeaturePermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            self.staff.feature_permissions.add(perm)
        self.client = tenant_client(tenant_host(self.ours))
        self.client.force_login(self.staff)

    def _school_with_cash_payment(self, tag, reference):
        school = School.objects.create(
            name=f"School {tag}",
            slug=f"pay-scope-{tag}",
            subdomain=f"pay-scope-{tag}",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        student = StudentProfile.objects.create(
            school=school,
            academic_year=year,
            first_name=tag.capitalize(),
            last_name="Payer",
            student_code=f"PS-{tag.upper()}",
        )
        invoice = Invoice.objects.create(
            school=school,
            profile=self.profile,
            academic_year=year,
            student=student,
            reference=reference,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=5),
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )
        payment = Payment.objects.create(
            school=school,
            invoice=invoice,
            student=student,
            amount=Decimal("100.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at=timezone.now(),
        )
        return school, payment

    def test_the_payment_list_shows_only_this_school(self):
        response = self.client.get(reverse("finance:payments"))
        assert_resolved_urlconf(response, TENANT_URLCONF)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.our_payment.invoice.reference)
        self.assertNotContains(
            response,
            self.their_payment.invoice.reference,
            msg_prefix=(
                "another school's receipt reached this page -- both schools share one "
                "ComplianceProfile, which bounds by COUNTRY"
            ),
        )

    def test_the_cash_closure_counts_only_this_school_s_cash(self):
        """The discrepancy this page reports is a number a bursar is held to."""
        response = self.client.get(reverse("finance:cash_office_closure"))
        self.assertEqual(response.status_code, 200)
        collected = response.context["cash_collected"]
        self.assertEqual(
            Decimal(collected),
            Decimal("100.00"),
            "cash_collected summed a co-located school's takings into this school's "
            "closure; each school banked 100.00, so 200.00 means the leak is open",
        )

    def test_the_payment_list_refuses_a_request_carrying_no_school(self):
        from django.test import RequestFactory

        from apps.finance.views_payments import payment_list

        request = RequestFactory().get("/finance/payments/")
        request.user = self.staff
        request.school = None
        self.assertEqual(payment_list(request).status_code, 403)


@override_settings(**HOST_ROUTED_SETTINGS)
class FinanceAccessGrantIsSchoolScopedTests(TestCase):
    """The IDOR: a POSTed student_id that the view then GRANTS access for."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="CM", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.ours = self._school("ours")
        self.theirs = self._school("theirs")
        self.their_student = self._student(self.theirs, "theirs")
        self.their_guardian_link = self._guardian(self.their_student, "theirs")

        self.staff = User.objects.create_user(
            username="access_staff", password="pass1234", role=User.Role.ACCOUNTANT
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        SchoolMembership.objects.get_or_create(
            user=self.staff,
            school=self.ours,
            defaults={"role": User.Role.ACCOUNTANT, "is_primary": True},
        )
        self.client = tenant_client(tenant_host(self.ours))
        self.client.force_login(self.staff)

    def _school(self, tag):
        return School.objects.create(
            name=f"School {tag}",
            slug=f"access-scope-{tag}",
            subdomain=f"access-scope-{tag}",
            is_active=True,
        )

    def _student(self, school, tag):
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        return StudentProfile.objects.create(
            school=school,
            academic_year=year,
            first_name=tag.capitalize(),
            last_name="Pupil",
            student_code=f"AS-{tag.upper()}",
        )

    def _guardian(self, student, tag):
        user = User.objects.create_user(
            username=f"{tag}_guardian",
            email=f"{tag}_guardian@example.test",
            password="pass1234",
            role=User.Role.PARENT,
        )
        return StudentGuardian.objects.create(
            guardian_user=user,
            student=student,
            relationship=StudentGuardian.Relationship.FATHER,
            can_view_finance=False,
        )

    def test_staff_cannot_grant_finance_access_to_another_school_s_guardians(self):
        self.assertFalse(self.their_guardian_link.can_view_finance)

        self.client.post(
            reverse("finance:finance_request_access"),
            {"student_id": str(self.their_student.pk)},
        )

        self.their_guardian_link.refresh_from_db()
        self.assertFalse(
            self.their_guardian_link.can_view_finance,
            "a staff member at one school granted another school's guardian access to "
            "that school's invoices -- student_id came from POST and was never bounded",
        )

    def test_the_same_grant_still_works_within_the_school(self):
        """The fix must not break the legitimate case it is guarding."""
        our_student = self._student(self.ours, "ours")
        our_link = self._guardian(our_student, "ours")
        self.assertFalse(our_link.can_view_finance)

        self.client.post(
            reverse("finance:finance_request_access"),
            {"student_id": str(our_student.pk)},
        )

        our_link.refresh_from_db()
        self.assertTrue(
            our_link.can_view_finance,
            "scoping the lookup broke the in-school grant it was meant to preserve",
        )
