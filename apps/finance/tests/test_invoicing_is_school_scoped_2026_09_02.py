"""The invoice list and fee generation are bounded by school, not by country.

``ComplianceProfile`` carries a ``country_code`` and **no** school column, so
``Invoice.objects.filter(profile=profile)`` in ``invoice_list`` bounded the page to a
COUNTRY. A parent was saved by the guardian filter that runs afterwards; a staff member
was not, and on a shared-schema box saw every co-located school's invoices. The query
carried ``# tenant-isolation-allow: scoped-via-surrounding-tenant-context``, and no
surrounding context bounded it.

``generate_fees`` was worse, because it is a WRITE path: it read
``FeePlan.objects.filter(is_active=True)`` with no scope at all, so a generation run
could bill this school's students against another school's fee plans.

Both models carry a school FK; neither was using it.

The existing coverage could not have caught either. It ran on the default ``testserver``
host, where ``request.school`` is None -- so there was no second school to leak from,
and the school-scoping the page now does had nothing to be measured against.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.accounts.models import Permission as FeaturePermission, User
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School, SchoolMembership
from apps.test_utils.tenant_hosts import (
    TENANT_URLCONF,
    HOST_ROUTED_SETTINGS,
    assert_resolved_urlconf,
    tenant_client,
    tenant_host,
)


@override_settings(**HOST_ROUTED_SETTINGS)
class InvoiceListIsSchoolScopedTests(TestCase):
    """Two schools sharing ONE ComplianceProfile -- i.e. the same country."""

    def setUp(self):
        # One profile for both schools is the whole point: it is what "scoped by
        # profile" actually bought, and it is the ordinary case for two schools in
        # the same country.
        self.profile = ComplianceProfile.objects.create(name="CM", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.ours, self.our_invoice = self._school_with_invoice("ours", "INV-OURS-1")
        self.theirs, self.their_invoice = self._school_with_invoice("theirs", "INV-THEIRS-1")

        self.staff = User.objects.create_user(
            username="scoped_staff", password="pass1234", role=User.Role.ACCOUNTANT
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        SchoolMembership.objects.get_or_create(
            user=self.staff,
            school=self.ours,
            defaults={"role": User.Role.ACCOUNTANT, "is_primary": True},
        )
        perm, _ = FeaturePermission.objects.get_or_create(
            code="finance.manage", defaults={"name": "Manage finance"}
        )
        self.staff.feature_permissions.add(perm)

        self.client = tenant_client(tenant_host(self.ours))
        self.client.force_login(self.staff)

    def _school_with_invoice(self, tag, reference):
        school = School.objects.create(
            name=f"School {tag}",
            slug=f"invoice-scope-{tag}",
            subdomain=f"invoice-scope-{tag}",
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
            last_name="Learner",
            student_code=f"IS-{tag.upper()}",
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
        return school, invoice

    def test_staff_see_their_own_school_s_invoices(self):
        response = self.client.get(reverse("finance:invoices"))
        assert_resolved_urlconf(response, TENANT_URLCONF)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.our_invoice.reference)

    def test_staff_do_not_see_a_co_located_school_s_invoices(self):
        """Same country, same ComplianceProfile, different school."""
        response = self.client.get(reverse("finance:invoices"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            self.their_invoice.reference,
            msg_prefix=(
                "another school's invoice reached this page -- filter(profile=...) "
                "bounds by COUNTRY, and both schools share one ComplianceProfile"
            ),
        )

    def test_the_view_refuses_a_request_carrying_no_school(self):
        from django.test import RequestFactory

        from apps.finance.views_invoicing import invoice_list

        request = RequestFactory().get("/finance/invoices/")
        request.user = self.staff
        request.school = None
        response = invoice_list(request)
        self.assertEqual(response.status_code, 403)


@override_settings(**HOST_ROUTED_SETTINGS)
class GenerateFeesIsSchoolScopedTests(TestCase):
    """The write path: which fee plans a generation run is allowed to read."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="CM", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"compliance_profile_id": self.profile.pk},
        )
        self.ours = School.objects.create(
            name="Fees ours",
            slug="fees-ours",
            subdomain="fees-ours",
            is_active=True,
        )
        self.theirs = School.objects.create(
            name="Fees theirs",
            slug="fees-theirs",
            subdomain="fees-theirs",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="fees_staff", password="pass1234", role=User.Role.ACCOUNTANT
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        SchoolMembership.objects.get_or_create(
            user=self.staff,
            school=self.ours,
            defaults={"role": User.Role.ACCOUNTANT, "is_primary": True},
        )
        perm, _ = FeaturePermission.objects.get_or_create(
            code="finance.manage", defaults={"name": "Manage finance"}
        )
        self.staff.feature_permissions.add(perm)
        self.client = tenant_client(tenant_host(self.ours))
        self.client.force_login(self.staff)

    def _plan(self, school, name):
        from apps.academics.models import Classroom, Department, Specialty
        from apps.finance.models import FeePlan

        year = AcademicYear.objects.create(
            school=school,
            name=f"{name} year",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        # FeePlan.classroom is NOT NULL, and Classroom is unique on (school, code),
        # so the code has to be per-school or the second school collides.
        # Department.code and Specialty.code are per-school identifiers; the second
        # school must not reuse the first's or it collides on the unique index.
        department = Department.objects.create(
            school=school,
            name=f"{name} dept",
            code=f"{school.subdomain}-d1",
        )
        specialty = Specialty.objects.create(
            school=school,
            department=department,
            name=f"{name} spec",
            code=f"{school.subdomain}-s1",
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=department,
            name=f"{name} class",
            code=f"{school.subdomain}-c1",
        )
        return FeePlan.objects.create(
            school=school,
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
            name=name,
            is_active=True,
        )

    def test_only_this_school_s_fee_plans_are_offered(self):
        ours = self._plan(self.ours, "Ours plan")
        theirs = self._plan(self.theirs, "Theirs plan")
        response = self.client.get(reverse("finance:generate_fees"))
        assert_resolved_urlconf(response, TENANT_URLCONF)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ours.name)
        self.assertNotContains(
            response,
            theirs.name,
            msg_prefix=(
                "another school's fee plan was offered on a page that GENERATES "
                "invoices from the plan you pick"
            ),
        )

    def test_the_view_refuses_a_request_carrying_no_school(self):
        from django.test import RequestFactory

        from apps.finance.views_invoicing import generate_fees

        request = RequestFactory().get("/finance/generate-fees/")
        request.user = self.staff
        request.school = None
        response = generate_fees(request)
        self.assertEqual(response.status_code, 403)
