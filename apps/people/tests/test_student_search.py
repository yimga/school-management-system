"""Student list search: index builder + queryset filter."""

from django.test import TestCase

from apps.people.models import StudentProfile
from apps.people.student_search import filter_students_by_search
from apps.people.student_search_index import build_student_search_index
from apps.schools.models import School


class StudentSearchTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Search School",
            slug="search-school",
            subdomain="search-school",
            is_active=True,
        )
        self.alice = StudentProfile.objects.create(
            school=self.school,
            first_name="Alice",
            last_name="Wonder",
            student_code="STU-ALICE-1",
            admission_number="ADM-9001",
            is_active=True,
        )
        self.bob = StudentProfile.objects.create(
            school=self.school,
            first_name="Bob",
            last_name="Builder",
            student_code="STU-BOB-2",
            is_active=True,
        )

    def test_build_search_index_includes_codes(self):
        idx = build_student_search_index(self.alice)
        self.assertIn("alice", idx)
        self.assertIn("adm-9001", idx)

    def test_filter_finds_by_admission_number(self):
        qs = StudentProfile.objects.filter(school=self.school, is_active=True)
        found = list(filter_students_by_search(qs, "ADM-9001"))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].pk, self.alice.pk)

    def test_filter_multi_token_and_semantics(self):
        qs = StudentProfile.objects.filter(school=self.school, is_active=True)
        found = list(filter_students_by_search(qs, "alice wonder"))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].pk, self.alice.pk)
        self.assertEqual(
            list(filter_students_by_search(qs, "alice builder")),
            [],
        )

    def test_save_refreshes_search_index(self):
        self.alice.last_name = "Updated"
        self.alice.save()
        self.alice.refresh_from_db()
        self.assertIn("updated", self.alice.search_index)
