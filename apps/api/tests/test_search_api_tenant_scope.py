import uuid

from django.test import TestCase, tag

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Subject
from apps.api.search_api import GlobalSearchAPI
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass, rls_school


@tag("tenants_rls")
class SearchApiTenantScopeTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.school_a = School.objects.create(
                name="School A",
                slug="school-a",
                subdomain="school-a",
                is_active=True,
            )
            self.school_b = School.objects.create(
                name="School B",
                slug="school-b",
                subdomain="school-b",
                is_active=True,
            )
            self.user = User.objects.create_user(
                username="search-admin",
                password="x",
                role=User.Role.ADMIN,
            )
            self.search_api = GlobalSearchAPI()
            Subject.objects.create(
                school=self.school_a,
                name="Mathematics",
                category=Subject.Category.GENERAL,
            )
            Subject.objects.create(
                school=self.school_b,
                name="Mathematics",
                category=Subject.Category.GENERAL,
            )

    def test_subject_search_is_tenant_scoped(self):
        with rls_school(self.school_a.id):
            results = self.search_api._search_type(
                self.search_api.SEARCH_CONFIG["subject"],
                query="Math",
                limit=10,
                user=self.user,
                school=self.school_a,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Mathematics")

    def test_enrich_student_stories_accepts_string_student_pk(self):
        """Story cards: search hits may serialize student id as string; ORM must still resolve."""
        with rls_bypass():
            year = AcademicYear.objects.create(
                name="Y1",
                starts_on="2024-01-01",
                ends_on="2024-12-31",
                school=self.school_a,
            )
            uq = uuid.uuid4().hex[:8]
            dept = Department.objects.create(
                name="Dept", code=f"D-{uq}", school=self.school_a
            )
            classroom = Classroom.objects.create(
                school=self.school_a,
                academic_year=year,
                department=dept,
                name="C1",
                code=f"C1-{uq}",
            )
            student = StudentProfile.objects.create(
                school=self.school_a,
                academic_year=year,
                classroom=classroom,
                first_name="Ada",
                last_name="Lovelace",
                student_code=f"STU-STORY-{uq}",
            )
            user = User.objects.create_user(
                username="story-admin",
                password="x",
                role=User.Role.ADMIN,
            )
        raw = [{"id": str(student.pk), "type": "student"}]
        with rls_school(self.school_a.id):
            out = self.search_api._enrich_student_stories(raw, self.school_a, user)
        self.assertEqual(len(out), 1)
        self.assertIn("story", out[0])
        self.assertIn("academic_line", out[0]["story"])
