from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.people.models import StudentProfile, StudentGuardian


class LinkChildTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            academic_year=self.year,
            name=Term.Name.FIRST,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=self.department,
        )
        self.student = StudentProfile.objects.create(
            first_name="Kid",
            last_name="One",
            student_code="STD100",
            admission_number="25GIL0001GENF1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.parent_user = User.objects.create_user(username="parent", password="pass")
        self.parent_user.role = User.Role.PARENT
        self.parent_user.save(update_fields=["role"])

    def test_link_child_updates_student_and_guardian_records(self):
        self.client.force_login(self.parent_user)
        data = {
            "admission_number": self.student.admission_number,
            "relationship": StudentGuardian.Relationship.GUARDIAN,
            "phone": "+237600000000",
            "preferred_contact": StudentGuardian.PreferredContact.WHATSAPP,
            "referral_code": "REF-TEST",
            "student_date_of_birth": "2010-05-01",
            "student_place_of_birth": "Yaounde",
            "student_gender": StudentProfile.Gender.FEMALE,
            "student_status": StudentProfile.Status.NEW,
            "student_joined_term": Term.Name.FIRST,
            "student_joined_date": "2025-09-01",
            "parent_first_name": "Jane",
            "parent_last_name": "Doe",
            "parent_email": "jane@example.com",
            "parent_whatsapp": "+237699999999",
            "parent_address": "Buea",
            "can_view_results": "on",
            "can_view_finance": "on",
        }
        # Use legacy single-page link_child so one POST completes the flow (link_child is now wizard)
        resp = self.client.post(reverse("portal:link_child_legacy"), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("portal:parent_dashboard"))
        student = StudentProfile.objects.get(pk=self.student.pk)
        self.assertEqual(student.gender, StudentProfile.Gender.FEMALE)
        self.assertEqual(student.place_of_birth, "Yaounde")
        self.assertEqual(student.status, StudentProfile.Status.NEW)
        self.assertEqual(student.joined_term, Term.Name.FIRST)

        guardian = StudentGuardian.objects.get(
            guardian_user=self.parent_user, student=student
        )
        self.assertEqual(guardian.email, "jane@example.com")
        self.assertEqual(guardian.whatsapp_number, "+237699999999")

        parent = User.objects.get(pk=self.parent_user.pk)
        self.assertEqual(parent.first_name, "Jane")
        self.assertEqual(parent.last_name, "Doe")
