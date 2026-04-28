"""North Star SLICE 6 — student attendance CSV export (tenant-scoped)."""

from datetime import date
import csv
import io
import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.portal.attendance_exports import (
    build_student_attendance_export_queryset,
    parse_export_filters_from_get,
)
from apps.schools.models import School, SchoolMembership


_HOST = "ns6sae.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST],
)
class StudentAttendanceExportSlice6Tests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Export School A",
            slug="ns6sae",
            subdomain="ns6sae",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Other School B",
            slug="ns6other",
            subdomain="ns6other",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school_a,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school_a,
            academic_year=cls.year,
            name="T1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 20),
            position=1,
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school_a,
            name="Core",
            code=f"NS6-{uuid.uuid4().hex[:6]}",
        )
        cls.spec = Specialty.objects.create(department=cls.dept, name="Gen", code="G")
        cls.classroom = Classroom.objects.create(
            school=cls.school_a,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 1A",
            code=f"F1A-{uuid.uuid4().hex[:6]}",
        )
        cls.classroom_b = Classroom.objects.create(
            school=cls.school_a,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 2B",
            code=f"F2B-{uuid.uuid4().hex[:6]}",
        )
        su = f"Mathematics {uuid.uuid4().hex[:8]}"
        cls.subject = Subject.objects.create(
            school=cls.school_a,
            name=su,
            category=Subject.Category.GENERAL,
        )
        cls.sa = SubjectAssignment.objects.create(
            school=cls.school_a,
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.spec,
            subject=cls.subject,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Ali",
            last_name="Zed",
            student_code=f"ST-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-001",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=cls.spec,
            date_of_birth=date(2010, 3, 1),
            is_active=True,
        )
        cls.att_march = Attendance.objects.create(
            school=cls.school_a,
            student=cls.student,
            classroom=cls.classroom,
            date=date(2025, 10, 1),
            status=Attendance.Status.PRESENT,
            remarks="",
        )
        cls.att_late = Attendance.objects.create(
            school=cls.school_a,
            student=cls.student,
            classroom=cls.classroom,
            date=date(2025, 10, 2),
            status=Attendance.Status.LATE,
            remarks="Traffic",
        )
        cls.student_form2 = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Bea",
            last_name="FormTwo",
            student_code=f"ST2-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-F2",
            academic_year=cls.year,
            classroom=cls.classroom_b,
            specialty=cls.spec,
            date_of_birth=date(2010, 5, 5),
            is_active=True,
        )
        cls.att_form2 = Attendance.objects.create(
            school=cls.school_a,
            student=cls.student_form2,
            classroom=cls.classroom_b,
            date=date(2025, 10, 4),
            status=Attendance.Status.PRESENT,
            remarks="",
        )
        # Other tenant (must not appear in A's export)
        _yb = AcademicYear.objects.create(
            school=cls.school_b,
            name="B-year",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        _db = Department.objects.create(
            school=cls.school_b, name="BD", code=f"BD-{uuid.uuid4().hex[:6]}"
        )
        _spb = Specialty.objects.create(department=_db, name="Bg", code="B")
        cls.classroom_b_school = Classroom.objects.create(
            school=cls.school_b,
            academic_year=_yb,
            department=_db,
            name="B class",
            code=f"BC-{uuid.uuid4().hex[:6]}",
        )
        cls.student_b = StudentProfile.objects.create(
            school=cls.school_b,
            first_name="Other",
            last_name="Tenant",
            student_code="OTH-1",
            academic_year=_yb,
            classroom=cls.classroom_b_school,
            specialty=_spb,
            date_of_birth=date(2010, 1, 1),
            is_active=True,
        )
        Attendance.objects.create(
            school=cls.school_b,
            student=cls.student_b,
            classroom=cls.classroom_b_school,
            date=date(2025, 10, 1),
            status=Attendance.Status.ABSENT,
        )

        cls.admin = User.objects.create_user(
            username="adm_export",
            password="testpass12",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=cls.admin,
            school=cls.school_a,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        cls.teacher_user = User.objects.create_user(
            username="tch_export",
            password="testpass12",
            role=User.Role.TEACHER,
        )
        cls.teacher = TeacherProfile.objects.create(
            user=cls.teacher_user,
            school=cls.school_a,
        )
        TeacherAssignment.objects.create(
            school=cls.school_a,
            teacher=cls.teacher,
            academic_year=cls.year,
            subject_assignment=cls.sa,
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=cls.teacher_user,
            school=cls.school_a,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        cls.parent = User.objects.create_user(
            username="par_export",
            password="testpass12",
            role=User.Role.PARENT,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_HOST)

    def _url(self, name, **kwargs):
        return reverse(name, urlconf="config.tenant_urls", kwargs=kwargs)

    def test_authorized_admin_csv_contains_rows(self):
        self.client.force_login(self.admin)
        url = self._url("portal:student_attendance_export_csv")
        r = self.client.get(
            url,
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0].strip(), "text/csv")
        self.assertIn("student_attendance_ns6sae_", r["Content-Disposition"])
        body = r.content.decode("utf-8")
        rows = list(csv.reader(io.StringIO(body)))
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "date")
        data_rows = [x for x in rows[1:] if any(x)]
        filters, _ = parse_export_filters_from_get(
            {"start_date": "2025-10-01", "end_date": "2025-10-31"}
        )
        assert filters is not None
        exp_qs, qerr = build_student_attendance_export_queryset(
            self.school_a, self.admin, filters
        )
        self.assertIsNone(qerr)
        self.assertEqual(len(data_rows), exp_qs.count())
        self.assertIn("Zed", body)
        self.assertIn("Ali", body)

    def test_teacher_sees_only_assigned_class(self):
        Attendance.objects.create(
            school=self.school_a,
            student=self.student,
            classroom=self.classroom_b,
            date=date(2025, 10, 3),
            status=Attendance.Status.ABSENT,
        )
        self.client.force_login(self.teacher_user)
        url = self._url("portal:student_attendance_export_csv")
        r = self.client.get(
            url,
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Form 2B", r.content.decode("utf-8"))
        self.assertIn("Form 1A", r.content.decode("utf-8"))

    def test_parent_forbidden(self):
        self.client.force_login(self.parent)
        r = self.client.get(self._url("portal:student_attendance_export_csv"))
        self.assertEqual(r.status_code, 403)

    def test_staff_with_permission_but_no_membership_forbidden(self):
        u = User.objects.create_user(
            username=f"nomem_{uuid.uuid4().hex[:8]}",
            password="testpass12",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_login(u)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
            },
        )
        self.assertEqual(r.status_code, 403)

    def test_api_v1_attendance_export_forbidden_without_membership(self):
        u = User.objects.create_user(
            username=f"apidem_{uuid.uuid4().hex[:8]}",
            password="testpass12",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_login(u)
        r = self.client.get(
            "/api/v1/attendance/export",
            HTTP_HOST=_HOST,
        )
        self.assertEqual(r.status_code, 403)

    def test_tenant_scoped_no_other_school(self):
        self.client.force_login(self.admin)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
            },
        )
        self.assertNotIn("Other", r.content.decode("utf-8"))
        self.assertNotIn("OTH-1", r.content.decode("utf-8"))

    def test_date_range_filters(self):
        self.client.force_login(self.admin)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2025-10-02",
                "end_date": "2025-10-02",
            },
        )
        self.assertEqual(r.status_code, 200)
        lines = r.content.decode("utf-8").strip().splitlines()
        self.assertEqual(len([ln for ln in lines if ln.strip()]), 2)
        self.assertIn("2025-10-02", lines[1])
        self.assertNotIn("2025-10-01", "\n".join(lines[1:]))

    def test_invalid_date_range_bad_request(self):
        self.client.force_login(self.admin)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2025-12-01",
                "end_date": "2025-10-01",
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_empty_dataset_header_only(self):
        self.client.force_login(self.admin)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2020-01-01",
                "end_date": "2020-01-31",
            },
        )
        self.assertEqual(r.status_code, 200)
        lines = [ln for ln in r.content.decode("utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("date,"))

    def test_ui_renders_markers(self):
        self.client.force_login(self.admin)
        r = self.client.get(self._url("portal:student_attendance_export"))
        self.assertEqual(r.status_code, 200)
        b = r.content.decode("utf-8")
        self.assertIn('data-rmc-attendance-export="student-csv"', b)
        self.assertIn('data-cp-evidence-surface="student-attendance-export"', b)

    def test_anonymous_redirects_to_login_for_csv(self):
        r = self.client.get(self._url("portal:student_attendance_export_csv"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/authentication/login/", r["Location"])

    def test_student_filter_limits_rows(self):
        self.client.force_login(self.admin)
        url = self._url("portal:student_attendance_export_csv")
        r = self.client.get(
            url,
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "student_id": str(self.student.pk),
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertIn("Zed", body)
        self.assertNotIn("FormTwo", body)

    def test_classroom_filter_limits_rows(self):
        self.client.force_login(self.admin)
        url = self._url("portal:student_attendance_export_csv")
        r = self.client.get(
            url,
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "classroom_id": str(self.classroom_b.pk),
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertIn("FormTwo", body)
        self.assertNotIn("Zed", body)

    def test_csv_content_disposition_attachment(self):
        self.client.force_login(self.admin)
        r = self.client.get(
            self._url("portal:student_attendance_export_csv"),
            {
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
            },
        )
        self.assertEqual(r.status_code, 200)
        cd = r["Content-Disposition"]
        self.assertIn("attachment", cd.lower())
        self.assertIn(".csv", cd)
