"""List screens number their rows, and the numbers survive pagination.

Measured on 2026-09-04, before this change: of 389 screens in this codebase that
render a table of rows, THREE put a number in a cell. Nobody could say "check
number 218" about a 431-row student register, and an operator reconciling a
printed list against the screen had to count.

These tests render the real pages through the real tenant host, because that is
the only place the answer is decidable. A unit test on the partial would pass
while the column was missing from every page that never included it, and a
template that renders in isolation still gets the wrong urlconf on the wrong host
(``config.urls`` vs the tenant one), so a request that "works" in a naive test
can 404 or 302 in production.

The pagination case is the one that matters. ``forloop.counter`` restarts at 1 on
page 2, so a list numbered that way tells you row 51 is row 1 -- which is worse
than no number, because it looks like an answer.
"""

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.tenant_hosts import host_routed, tenant_host

PASSWORD = "row-number-probe-pw"


class _TenantListFixture(TestCase):
    """One school, enough rows to force a second page."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Row Number High",
            slug="row-number-high",
            subdomain="row-number-high",
            is_active=True,
            country_code="CM",
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school, name="2026", start_date="2026-01-01", end_date="2026-12-31"
        )
        cls.department = Department.objects.create(
            school=cls.school, name="Building Trades", code="BT"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school,
            name="Building Construction",
            code="BC",
            department=cls.department,
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            name="Form 1",
            code="F1",
            academic_year=cls.year,
            department=cls.department,
        )
        cls.admin = User.objects.create_user(
            username="rownum.admin",
            password=PASSWORD,
            role=User.Role.ADMIN,
            email="rownum.admin@example.com",
        )

    def setUp(self):
        self.host = tenant_host(self.school)
        self.client = login_tenant_admin_client(
            self.admin, password=PASSWORD, host=self.host, school=self.school
        )

    def _get(self, url_name, **params):
        url = reverse(url_name)
        if params:
            url += "?" + "&".join("%s=%s" % kv for kv in params.items())
        return self.client.get(url, HTTP_HOST=self.host)


@host_routed
class StudentListNumbersItsRowsTests(_TenantListFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for i in range(1, 31):
            StudentProfile.objects.create(
                school=cls.school,
                first_name="Student%02d" % i,
                last_name="Row",
                academic_year=cls.year,
                specialty=cls.specialty,
                classroom=cls.classroom,
                admission_number="ADM%03d" % i,
            )

    def test_the_list_renders_at_all(self):
        """A 302 here is membership or MFA, not the column -- fail loudly on it."""
        res = self._get("accounts:backend_student_list")
        self.assertEqual(res.status_code, 200, res.get("Location", ""))

    def test_the_page_carries_a_row_number_column(self):
        res = self._get("accounts:backend_student_list")
        html = res.content.decode("utf-8")
        self.assertIn('class="rmc-row-num-th"', html)
        self.assertIn("data-rmc-row-num", html)

    def test_the_first_page_starts_at_one(self):
        res = self._get("accounts:backend_student_list", page_size=10)
        html = res.content.decode("utf-8")
        self.assertIn(">1</td>", html)
        self.assertIn(">10</td>", html)

    def test_the_second_page_continues_instead_of_restarting(self):
        res = self._get("accounts:backend_student_list", page_size=10, page=2)
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        numbers = [
            n
            for n in range(1, 31)
            if ('data-rmc-row-num>%d</td>' % n) in html.replace(" ", "")
            or ('>%d</td>' % n) in html
        ]
        self.assertIn(11, numbers, "page 2 must begin at 11")
        self.assertNotIn(
            1,
            [n for n in numbers if n < 11],
            "page 2 restarted at 1 -- forloop.counter was used without start_index",
        )


@host_routed
class StaffAndGuardianListsNumberTheirRowsTests(_TenantListFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for i in range(1, 4):
            staff = User.objects.create_user(
                username="rownum.staff%d" % i,
                password=PASSWORD,
                role=User.Role.TEACHER,
            )
            TeacherProfile.objects.create(
                user=staff, school=cls.school, staff_id="EMP%02d" % i
            )
        # A guardian list with no guardians renders no table, so the assertion
        # would pass or fail on the fixture rather than on the column.
        child = StudentProfile.objects.create(
            school=cls.school,
            first_name="Ward",
            last_name="One",
            academic_year=cls.year,
            specialty=cls.specialty,
            classroom=cls.classroom,
            admission_number="ADMG01",
        )
        parent = User.objects.create_user(
            username="rownum.parent", password=PASSWORD, role=User.Role.PARENT
        )
        StudentGuardian.objects.create(
            guardian_user=parent, student=child, relationship="Father"
        )

    def test_teacher_list_is_numbered(self):
        res = self._get("accounts:backend_teacher_list")
        self.assertEqual(res.status_code, 200, res.get("Location", ""))
        html = res.content.decode("utf-8")
        self.assertIn('class="rmc-row-num-th"', html)
        self.assertIn("data-rmc-row-num", html)

    def test_guardian_list_is_numbered(self):
        res = self._get("accounts:backend_guardian_list")
        self.assertEqual(res.status_code, 200, res.get("Location", ""))
        self.assertIn('class="rmc-row-num-th"', res.content.decode("utf-8"))
