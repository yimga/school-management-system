from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User, AccessRole
from apps.accounts.permissions import has_role_hierarchy, can_view_invoice
from apps.academics.models import AcademicYear, Department, Specialty, Classroom
from apps.people.models import StudentProfile, StudentGuardian
from apps.finance.models import ComplianceProfile, Invoice
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.models import default_backend_feature_flags


class RoleHierarchyTests(TestCase):
    def test_teacher_not_principal(self):
        teacher = User.objects.create_user(
            username="teacher1",
            password="pass1234",
            role=User.Role.TEACHER,
        )
        self.assertFalse(has_role_hierarchy(teacher, "PRINCIPAL"))

    def test_admin_is_principal(self):
        admin = User.objects.create_user(
            username="admin1",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        self.assertTrue(has_role_hierarchy(admin, "PRINCIPAL"))

    def test_access_role_exact_match(self):
        user = User.objects.create_user(
            username="finance_user",
            password="pass1234",
            role=User.Role.PARENT,
        )
        role, _ = AccessRole.objects.get_or_create(
            code="BURSAR",
            defaults={"name": "Bursar"},
        )
        user.roles.add(role)
        self.assertTrue(has_role_hierarchy(user, "BURSAR"))


class InvoiceAccessTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )
        self.student = StudentProfile.objects.create(
            first_name="Jane",
            last_name="Student",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Default",
            country_code="CM",
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )

    def test_parent_can_view_own_invoice(self):
        parent = User.objects.create_user(
            username="parent1",
            password="pass1234",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=parent, student=self.student, can_view_finance=True
        )
        self.assertTrue(can_view_invoice(parent, self.invoice.id))

    def test_unrelated_parent_cannot_view_invoice(self):
        parent = User.objects.create_user(
            username="parent2",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.assertFalse(can_view_invoice(parent, self.invoice.id))


class GuardianFinanceOptInTests(TestCase):
    def setUp(self):
        site = get_platform_site_settings_record(create=True)
        flags = {
            **default_backend_feature_flags(),
            **(site.backend_feature_flags or {}),
        }
        flags["require_guardian_finance_opt_in"] = True
        site.backend_feature_flags = flags
        site.save()

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )
        self.profile = ComplianceProfile.objects.create(
            name="Default", country_code="CM"
        )
        self.student = StudentProfile.objects.create(
            first_name="Alex",
            last_name="Student",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )

    def test_parent_blocked_when_opt_in_required_and_not_granted(self):
        parent = User.objects.create_user(
            username="parent_no_opt_in",
            password="pass1234",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=parent, student=self.student, can_view_finance=False
        )
        self.assertFalse(can_view_invoice(parent, self.invoice.id))

    def test_parent_allowed_when_opt_in_disabled_even_if_flag_missing(self):
        parent = User.objects.create_user(
            username="parent_opt_out",
            password="pass1234",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=parent, student=self.student, can_view_finance=False
        )

        site = get_platform_site_settings_record(create=True)
        flags = {
            **default_backend_feature_flags(),
            **(site.backend_feature_flags or {}),
        }
        flags["require_guardian_finance_opt_in"] = False
        site.backend_feature_flags = flags
        site.save()

        self.assertTrue(can_view_invoice(parent, self.invoice.id))
