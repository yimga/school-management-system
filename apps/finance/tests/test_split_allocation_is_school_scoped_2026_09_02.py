"""Split allocation bills against the requesting school's year, and stamps its rows.

Three defects, all in ``apps/finance/views_payments.py::split_allocation``, all invisible
to the suite that covered it:

1. ``AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()`` --
   the field's own help text says "exactly one should be active PER SCHOOL", so
   unscoped this returns whichever school's year sorts first. It carried a
   ``tenant-isolation-allow`` marker reading "scoped-via-surrounding-tenant-context",
   and there was no such context: nothing upstream bounded it.
2. ``StudentProfile.objects.filter(academic_year=active_year)`` -- scoped only through
   that cross-tenant year, so the student picker could offer another school's students.
3. ``Invoice`` and ``Payment`` both carry a nullable ``school`` FK that this flow never
   set, so every row it wrote was orphaned from its tenant -- absent from a
   school-scoped invoice list, and on the RLS lane outside the policy's reach.

On the cloud each tenant has its own schema, which hides all three. On a sovereign box
every school shares one schema, where they are live.

The existing coverage could not see any of it: it ran on the default ``testserver``
host, where ``request.school`` is None, so there was no second school to leak from and
no school to compare a written row against. These tests bind a real tenant host.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

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
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.tenant_hosts import (
    HOST_ROUTED_SETTINGS,
    TENANT_URLCONF,
    assert_resolved_urlconf,
    tenant_host,
)


@override_settings(**HOST_ROUTED_SETTINGS)
class SplitAllocationIsSchoolScopedTests(TestCase):
    """Two schools, each with its own active year and student."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="Shared", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.perm, _ = FeaturePermission.objects.get_or_create(
            code="finance.manage", defaults={"name": "Manage finance"}
        )
        self.ours, self.our_year, self.our_student = self._school("ours", 2025)
        # The other school's year starts LATER, so an unscoped `.order_by("-start_date")`
        # returns it first. That ordering is what makes the leak deterministic rather
        # than incidental, and it is why this fixture pins the dates.
        self.theirs, self.their_year, self.their_student = self._school("theirs", 2026)
        self.staff = self._accountant("ours_accountant", self.ours)
        self.client = login_tenant_admin_client(
            self.staff,
            password="pass1234",
            host=tenant_host(self.ours),
            school=self.ours,
            role=User.Role.ACCOUNTANT,
        )

    def _school(self, tag, start_year):
        school = School.objects.create(
            name=f"School {tag}",
            slug=f"split-scope-{tag}",
            subdomain=f"split-scope-{tag}",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            school=school,
            name=f"{start_year}/{start_year + 1}",
            start_date=date(start_year, 9, 1),
            end_date=date(start_year + 1, 6, 30),
            is_active=True,
        )
        student = StudentProfile.objects.create(
            school=school,
            academic_year=year,
            first_name=tag.capitalize(),
            last_name="Learner",
            student_code=f"SC-{tag.upper()}",
        )
        return school, year, student

    def _accountant(self, username, school):
        user = User.objects.create_user(
            username=username, password="pass1234", role=User.Role.ACCOUNTANT
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        user.feature_permissions.add(self.perm)
        return user

    def _get(self):
        response = self.client.get(reverse("finance:split_allocation"))
        assert_resolved_urlconf(response, TENANT_URLCONF)
        return response

    def test_the_student_picker_offers_only_this_school(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        offered = {s.pk for s in response.context["form"].fields["student"].queryset}
        self.assertEqual(offered, {self.our_student.pk})
        self.assertNotIn(self.their_student.pk, offered)

    def test_the_active_year_is_this_school_s_year_not_the_latest_overall(self):
        """The other school's year starts later, so an unscoped read would win."""
        response = self._get()
        offered = list(response.context["form"].fields["student"].queryset)
        self.assertTrue(offered, "no students offered at all")
        self.assertTrue(
            all(s.academic_year_id == self.our_year.pk for s in offered),
            f"expected every offered student on {self.our_year}, got "
            f"{[(s.pk, s.academic_year_id) for s in offered]}",
        )

    def test_a_recorded_split_stamps_the_school_on_the_invoice_and_payment(self):
        guardian = User.objects.create_user(
            username="ours_guardian",
            email="ours_guardian@example.test",
            password="pass1234",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=guardian,
            student=self.our_student,
            relationship=StudentGuardian.Relationship.FATHER,
            can_view_finance=True,
        )
        self._get()  # prime the form/session the way the page is actually used
        response = self.client.post(
            reverse("finance:split_allocation"),
            {
                "student": str(self.our_student.pk),
                "total_amount": "25000.00",
                "method": PaymentMethodCode.choices[0][0],
                "split_mode": "equal",
                "desc_1": "Tuition",
                "amount_1": "25000.00",
            },
        )
        self.assertIn(response.status_code, (200, 302), response.status_code)
        invoice = Invoice.objects.filter(student=self.our_student).first()
        self.assertIsNotNone(
            invoice,
            "no invoice was written -- the form rejected the payload, so the school-stamping assertions below never ran",
        )
        self.assertEqual(
            invoice.school_id,
            self.ours.pk,
            "invoice was written without its school -- it is orphaned from the tenant, "
            "so a school-scoped invoice list will never show it",
        )
        payment = Payment.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.school_id, self.ours.pk)

    def test_the_page_is_not_mounted_on_the_public_host(self):
        """Defence in depth: the base domain never serves this route at all."""
        from apps.test_utils.tenant_hosts import PUBLIC_HOST, PUBLIC_URLCONF

        response = self.client.get(
            reverse("finance:split_allocation"), HTTP_HOST=PUBLIC_HOST
        )
        assert_resolved_urlconf(response, PUBLIC_URLCONF)
        self.assertEqual(response.status_code, 404)

    def test_the_view_itself_refuses_a_request_carrying_no_school(self):
        """The route guard, not the urlconf: reached with no school, it must refuse.

        Driven through RequestFactory because no host both mounts this route AND
        leaves request.school unset -- which is the point, but it means the guard
        would otherwise be unreachable and therefore untested.
        """
        from django.test import RequestFactory

        from apps.finance.views_payments import split_allocation

        request = RequestFactory().get("/finance/split-allocation/")
        request.user = self.staff
        request.school = None
        response = split_allocation(request)
        self.assertEqual(response.status_code, 403)
