"""
Cross-tenant HTTP isolation: staff contact queue must not expose another school’s ContactRequest.

GlobalSupportTicket is super-admin only; tenant admins do not use these tests — super URLs
are gated by require_super_access_with_host.
"""

from datetime import date

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, tag

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.communication.models import ContactRequest
from apps.people.models import StudentGuardian, StudentProfile
from apps.portal.views_contact_requests import staff_contact_request_list
from apps.schools.rls_context import rls_bypass, rls_school
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


@tag("tenants_rls")
class CrossModuleSupportIsolationTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.school_a = School.objects.create(
                slug="iso-a",
                subdomain="iso-a",
                name="School A",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.school_b = School.objects.create(
                slug="iso-b",
                subdomain="iso-b",
                name="School B",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            year_a = AcademicYear.objects.create(
                name="Y-A",
                start_date=date(2025, 9, 1),
                end_date=date(2026, 7, 1),
                is_active=True,
                school=self.school_a,
            )
            dept = Department.objects.create(
                name="D", code="D-ISO", school=self.school_a
            )
            classroom = Classroom.objects.create(
                academic_year=year_a,
                department=dept,
                name="C1",
                code="C1",
                school=self.school_a,
            )
            self.parent = User.objects.create_user(
                username="iso_parent", password="pass", role=User.Role.PARENT
            )
            student = StudentProfile.objects.create(
                first_name="Kid",
                last_name="A",
                student_code="ISO-001",
                academic_year=year_a,
                classroom=classroom,
                school=self.school_a,
                is_active=True,
            )
            StudentGuardian.objects.create(guardian_user=self.parent, student=student)
            self.secretary_b = User.objects.create_user(
                username="iso_sec_b",
                password="pass",
                role=User.Role.SECRETARY,
                is_staff=True,
            )
            # staff_contact_request_list is @tenant_admin_required: the actor must
            # be a tenant-admin of the school it acts on. Make secretary_b an owner
            # of school B so the view is reached and the isolation assertion (no
            # school A rows) actually runs -- under rls_school(B) the school A
            # ContactRequest is RLS-filtered, proving DB-layer isolation too.
            SchoolMembership.objects.create(
                user=self.secretary_b,
                school=self.school_b,
                role=User.Role.ADMIN,
                is_primary=True,
                is_school_owner=True,
            )
            ContactRequest.objects.create(
                parent=self.parent,
                student=student,
                school=self.school_a,
                contact_name="Guardian",
                subject="Secret from A",
                message="Do not leak",
                audience=ContactRequest.Audience.TEACHER,
                preferred_channel=ContactRequest.Channel.EMAIL,
            )

    def test_staff_on_school_b_sees_no_school_a_requests(self):
        rf = RequestFactory()
        request = rf.get("/portal/staff/contact-requests/")
        request.user = self.secretary_b
        request.school = self.school_b
        SessionMiddleware(lambda r: HttpResponse()).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        with rls_school(self.school_b.id):
            response = staff_contact_request_list(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("No contact requests found", body)
        self.assertNotIn("Secret from A", body)
