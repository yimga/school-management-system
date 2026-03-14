from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Department, Specialty, Classroom
from apps.people.models import StudentProfile, StudentGuardian
from apps.finance.models import ComplianceProfile, Invoice, Notification
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.models import SiteSettings, default_backend_feature_flags
from apps.communication.models import Message


class FinanceAccessRequestTests(TestCase):
    def setUp(self):
        site = get_platform_site_settings_record(create=True)
        flags = {**default_backend_feature_flags(), **(site.backend_feature_flags or {})}
        flags["allow_finance_access_requests"] = True
        flags["require_guardian_finance_opt_in"] = True
        SiteSettings.objects.filter(pk=site.pk).update(backend_feature_flags=flags)
        # Clear site settings cache so the view sees updated flags
        from apps.siteconfig.models import _clear_site_settings_cache
        _clear_site_settings_cache(SiteSettings)

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.specialty = Specialty.objects.create(name="General", code="GEN", department=self.department)
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )
        self.profile = ComplianceProfile.objects.create(name="Default", country_code="CM")
        self.student = StudentProfile.objects.create(
            first_name="Jordan",
            last_name="Learner",
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
        self.parent = User.objects.create_user(
            username="parent_req",
            password="pass1234",
        )
        self.parent.role = User.Role.PARENT
        self.parent.save(update_fields=["role"])
        self.admin = User.objects.create_user(
            username="admin_rec",
            password="pass1234",
            role=User.Role.ADMIN,
        )

    def test_parent_can_request_access_when_enabled(self):
        StudentGuardian.objects.create(guardian_user=self.parent, student=self.student, can_view_finance=False)

        self.client.force_login(self.parent)
        resp = self.client.post(reverse("finance:invoice_request_access", args=[self.invoice.id]))

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Message.objects.filter(recipient=self.admin, subject__icontains="Finance access request").exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.admin, title="Finance access request").exists()
        )

    def test_request_access_disabled_flag_blocks(self):
        site = get_platform_site_settings_record(create=True)
        flags = {**default_backend_feature_flags(), **(site.backend_feature_flags or {})}
        flags["allow_finance_access_requests"] = False
        site.backend_feature_flags = flags
        site.save()

        StudentGuardian.objects.create(guardian_user=self.parent, student=self.student, can_view_finance=False)

        self.client.force_login(self.parent)
        resp = self.client.post(reverse("finance:finance_request_access"))

        self.assertEqual(resp.status_code, 403)
