from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Department, Classroom, Specialty, Term, Subject, SubjectAssignment
from apps.evals.models import TeacherAssignment
from apps.people.models import StudentProfile, StudentGuardian, TeacherProfile


class DashboardApiRbacTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2024-2025",
            starts_on="2024-01-01",
            ends_on="2024-12-31",
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1A",
            code="F1A",
        )
        self.specialty = Specialty.objects.create(
            department=self.department,
            name="General Studies",
            code="GEN-ST",
        )
        self.other_specialty = Specialty.objects.create(
            department=self.department,
            name="Science Track",
            code="SCI-TR",
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="FIRST",
            start_date="2024-01-01",
            end_date="2024-03-31",
            position=1,
            is_active=True,
        )
        self.subject = Subject.objects.create(name="Mathematics", category=Subject.Category.GENERAL)

        self.parent_user = User.objects.create_user(
            username="parent_api",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_api",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.teacher_profile = TeacherProfile.objects.create(
            user=self.teacher_user,
            department=self.department,
        )
        self.student = StudentProfile.objects.create(
            first_name="Student",
            last_name="One",
            date_of_birth="2010-01-01",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        StudentProfile.objects.create(
            first_name="Student",
            last_name="Two",
            date_of_birth="2010-02-01",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.other_specialty,
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_results=True,
            can_view_finance=True,
        )
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher_profile,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
        )

    def test_parent_dashboard_api_allows_parent(self):
        self.client.force_login(self.parent_user)
        response = self.client.get("/api/dashboard/parent/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("children_count"), 1)

    def test_parent_dashboard_api_denies_non_parent(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get("/api/dashboard/parent/")
        self.assertEqual(response.status_code, 403)

    def test_teacher_dashboard_api_filters_students_by_assignment(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get("/api/dashboard/teacher/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("my_students"), 1)
        self.assertEqual(payload.get("my_classes"), 1)
