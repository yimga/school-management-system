from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Subject, SubjectAssignment, Term
from apps.evals.models import Evaluation, TeacherAssignment
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.siteconfig.models import SiteSettings
from emis.services import EMISExportService


class EMISExportServiceTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="FIRST",
            custom_label="Term 1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 20),
            position=1,
            is_active=True,
        )
        self.department = Department.objects.create(name="Technical", code="TECH")
        self.specialty = Specialty.objects.create(department=self.department, name="Carpentry", code="CARP")
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form Three",
            code="F3A",
        )
        self.subject = Subject.objects.create(name="Technology of Materials", category=Subject.Category.PROFESSIONAL)
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=2,
        )

        self.teacher_user = User.objects.create_user(
            username="teacher_emis",
            password="pass1234",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            department=self.department,
            position_title="Technical Teacher",
            phone="670000000",
            staff_id="T-0001",
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )

        self.student = StudentProfile.objects.create(
            first_name="Abajo",
            last_name="Jeffter",
            student_code="ST001",
            date_of_birth=date(2011, 3, 8),
            gender=StudentProfile.Gender.MALE,
            joined_date=date(2025, 9, 1),
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            exam_candidate_number="23GIL0016CJ1",
            exam_center_code="GCE-01",
            exam_system="GCE",
            is_active=True,
        )
        self.guardian_user = User.objects.create_user(
            username="guardian_emis",
            password="pass1234",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            phone="677000000",
            can_view_results=True,
            can_view_finance=True,
        )
        Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("12.00"),
            seq2_score=Decimal("13.00"),
            exam_score=Decimal("14.00"),
        )

        site = SiteSettings.get_solo()
        site.site_name = "Gilead Technical High School"
        site.school_code = "GIL"
        site.company_address = "Small Soppo, Buea"
        site.country = "Cameroon"
        site.save(update_fields=["site_name", "school_code", "company_address", "country"])

    def test_exports_are_schema_safe(self):
        service = EMISExportService("CMR")
        students = service.export_students(self.year, self.term)
        teachers = service.export_teachers(self.year, self.term)
        subjects = service.export_subjects(self.year, self.term)
        enrollment = service.export_enrollment(self.year, self.term)
        performance = service.export_performance(self.year, self.term)
        infra = service.export_infrastructure()

        self.assertEqual(students["count"], 1)
        self.assertEqual(teachers["count"], 1)
        self.assertEqual(subjects["count"], 1)
        self.assertEqual(enrollment["count"], 1)
        self.assertEqual(performance["count"], 1)
        self.assertEqual(infra["count"], 1)
        self.assertIn("student_id", students["data"][0])
        self.assertIn("teacher_id", teachers["data"][0])
        self.assertIn("subject_name", subjects["data"][0])
        self.assertIn("average_performance", performance["data"][0])

    def test_dashboard_view_renders_without_subject_field_errors(self):
        admin = User.objects.create_user(
            username="admin_emis",
            password="pass1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("emis:dashboard"))
        self.assertEqual(response.status_code, 200)
