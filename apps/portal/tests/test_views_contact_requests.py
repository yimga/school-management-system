"""HTTP-style tests for parent Contact School and staff contact-request triage views."""

from datetime import date
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.communication.models import ContactRequest
from apps.people.models import StudentGuardian, StudentProfile
from apps.portal.views_contact_requests import (
    parent_contact_school,
    staff_contact_request_detail,
    staff_contact_request_list,
)
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


def _attach_session_and_messages(request):
    SessionMiddleware(lambda r: HttpResponse()).process_request(request)
    request.session.save()
    setattr(request, "_messages", FallbackStorage(request))


class ContactRequestPortalViewTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="cr-portal-school",
            subdomain="cr-portal-school",
            name="CR Portal School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
            school=self.school,
        )
        self.dept = Department.objects.create(
            name="Dept",
            code="D-CR",
            school=self.school,
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.dept,
            name="Form 1",
            code="F1-CR",
            school=self.school,
        )
        self.parent = User.objects.create_user(
            username="cr_parent",
            password="pass",
            role=User.Role.PARENT,
        )
        self.student = StudentProfile.objects.create(
            first_name="Sam",
            last_name="Student",
            student_code="CR-STU-001",
            academic_year=self.year,
            classroom=self.classroom,
            school=self.school,
            is_active=True,
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
        )
        self.secretary = User.objects.create_user(
            username="cr_secretary",
            password="pass",
            role=User.Role.SECRETARY,
            is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username="cr_teacher",
            password="pass",
            role=User.Role.TEACHER,
            is_staff=True,
        )

    @patch("apps.portal.views_contact_requests._pick_triage_owner")
    def test_parent_post_creates_contact_with_request_school(self, mock_pick):
        mock_pick.return_value = self.secretary
        rf = RequestFactory()
        path = reverse("portal:parent_contact_school")
        data = {
            "student": str(self.student.pk),
            "contact_name": "Pat Parent",
            "contact_email": "pat@example.com",
            "audience": ContactRequest.Audience.TEACHER,
            "preferred_channel": ContactRequest.Channel.EMAIL,
            "subject": "Meeting",
            "message": "Please call me Tuesday.",
        }
        request = rf.post(path, data=data)
        request.user = self.parent
        request.school = self.school
        _attach_session_and_messages(request)
        response = parent_contact_school(request)
        self.assertEqual(response.status_code, 302)
        cr = ContactRequest.objects.get(parent=self.parent)
        self.assertEqual(cr.school_id, self.school.id)
        self.assertEqual(cr.status, ContactRequest.Status.OPEN)

    def test_staff_list_scoped_to_request_school(self):
        other = School.objects.create(
            slug="cr-other",
            subdomain="cr-other",
            name="Other",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        ContactRequest.objects.create(
            parent=self.parent,
            student=self.student,
            school=self.school,
            contact_name="A",
            subject="For school A",
            message="Hi",
            audience=ContactRequest.Audience.TEACHER,
            preferred_channel=ContactRequest.Channel.EMAIL,
        )
        ContactRequest.objects.create(
            parent=self.parent,
            student=None,
            school=other,
            contact_name="B",
            subject="For other",
            message="Hi",
            audience=ContactRequest.Audience.TEACHER,
            preferred_channel=ContactRequest.Channel.EMAIL,
        )
        rf = RequestFactory()
        request = rf.get(reverse("portal:staff_contact_request_list"))
        request.user = self.secretary
        request.school = self.school
        _attach_session_and_messages(request)
        response = staff_contact_request_list(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("For school A", body)
        self.assertNotIn("For other", body)

    def test_non_triage_staff_forbidden(self):
        rf = RequestFactory()
        request = rf.get(reverse("portal:staff_contact_request_list"))
        request.user = self.teacher
        request.school = self.school
        _attach_session_and_messages(request)
        response = staff_contact_request_list(request)
        self.assertEqual(response.status_code, 403)

    def test_detail_404_for_wrong_school(self):
        other = School.objects.create(
            slug="cr-other2",
            subdomain="cr-other2",
            name="Other2",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        cr = ContactRequest.objects.create(
            parent=self.parent,
            student=self.student,
            school=self.school,
            contact_name="A",
            subject="Scoped",
            message="Body",
            audience=ContactRequest.Audience.TEACHER,
            preferred_channel=ContactRequest.Channel.EMAIL,
        )
        rf = RequestFactory()
        request = rf.get("/")
        request.user = self.secretary
        request.school = other
        _attach_session_and_messages(request)
        with self.assertRaises(Http404):
            staff_contact_request_detail(request, str(cr.id))

    def test_assign_and_status_post(self):
        cr = ContactRequest.objects.create(
            parent=self.parent,
            student=self.student,
            school=self.school,
            contact_name="A",
            subject="Triage me",
            message="Body",
            audience=ContactRequest.Audience.TEACHER,
            preferred_channel=ContactRequest.Channel.EMAIL,
        )
        rf = RequestFactory()
        request = rf.post(
            "/",
            {"action": "assign", "assigned_to": str(self.secretary.pk), "triage_notes": "ok"},
        )
        request.user = self.secretary
        request.school = self.school
        _attach_session_and_messages(request)
        response = staff_contact_request_detail(request, str(cr.id))
        self.assertEqual(response.status_code, 302)
        cr.refresh_from_db()
        self.assertEqual(cr.assigned_to_id, self.secretary.pk)
        self.assertEqual(cr.status, ContactRequest.Status.ASSIGNED)

        request2 = rf.post(
            "/",
            {
                "action": "status",
                "status": ContactRequest.Status.RESOLVED,
                "resolution_notes": "Done",
            },
        )
        request2.user = self.secretary
        request2.school = self.school
        _attach_session_and_messages(request2)
        staff_contact_request_detail(request2, str(cr.id))
        cr.refresh_from_db()
        self.assertEqual(cr.status, ContactRequest.Status.RESOLVED)
