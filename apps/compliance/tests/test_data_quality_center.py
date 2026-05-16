"""Wave 5 (v2.76): Data Quality Center — checks + view + tenant isolation."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.compliance.data_quality import (
    DATA_QUALITY_CHECKS,
    data_quality_checks,
    summarize,
)
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.schools.models import School


class DataQualityChecksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.school_a = School.objects.create(name="School A", slug="dq-a", subdomain="dq-a-sub")
        cls.school_b = School.objects.create(name="School B", slug="dq-b", subdomain="dq-b-sub")

        cls.parent_a = User.objects.create_user(
            username="parent_a", email="parent_a@example.com", password="pwd"
        )
        cls.parent_b = User.objects.create_user(
            username="parent_b", email="parent_b@example.com", password="pwd"
        )
        cls.teacher_user_disabled = User.objects.create_user(
            username="teacher_disabled", email="td@example.com", password="pwd"
        )
        cls.teacher_user_disabled.is_active = False
        cls.teacher_user_disabled.save(update_fields=["is_active"])
        cls.teacher_user_clean = User.objects.create_user(
            username="teacher_clean", email="tc@example.com", password="pwd"
        )

        # School A: 1 student WITHOUT guardian (blocker), 1 WITH guardian.
        cls.student_orphan_a = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Orphan",
            last_name="A",
            is_active=True,
            parent_phone="0700-000-000",
        )
        cls.student_linked_a = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Linked",
            last_name="A",
            is_active=True,
            parent_phone="0700-111-222",
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent_a, student=cls.student_linked_a
        )

        # School A: 1 teacher whose login is disabled (blocker).
        cls.teacher_disabled_a = TeacherProfile.objects.create(
            school=cls.school_a,
            user=cls.teacher_user_disabled,
            is_active=True,
        )

        # School A: 1 student with no parent phone (info).
        cls.student_no_phone = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="NoPhone",
            last_name="A",
            is_active=True,
            parent_phone="",
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent_a, student=cls.student_no_phone
        )

        # School B: clean — 1 student WITH guardian and phone, 1 teacher WITH user.
        cls.student_clean_b = StudentProfile.objects.create(
            school=cls.school_b,
            first_name="Clean",
            last_name="B",
            is_active=True,
            parent_phone="0800-333-444",
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent_b, student=cls.student_clean_b
        )
        cls.teacher_clean_b = TeacherProfile.objects.create(
            school=cls.school_b,
            user=cls.teacher_user_clean,
            is_active=True,
        )

    def test_school_a_has_expected_issues(self):
        issues = data_quality_checks(school=self.school_a)
        keys = {i["key"] for i in issues}
        self.assertIn("students_without_guardian", keys)
        self.assertIn("teachers_with_disabled_login", keys)
        self.assertIn("students_without_parent_phone", keys)

    def test_school_a_orphan_student_in_sample(self):
        issues = data_quality_checks(school=self.school_a)
        students_no_guardian = next(
            i for i in issues if i["key"] == "students_without_guardian"
        )
        self.assertEqual(students_no_guardian["record_count"], 1)
        self.assertIn(self.student_orphan_a.id, students_no_guardian["record_sample_ids"])

    def test_school_b_is_clean(self):
        issues = data_quality_checks(school=self.school_b)
        keys = {i["key"] for i in issues}
        # Clean school should have NO issues from the three checks above.
        # students_without_classroom may still fire because classroom is nullable;
        # accept that one specifically while asserting the others are absent.
        self.assertNotIn("students_without_guardian", keys)
        self.assertNotIn("teachers_with_disabled_login", keys)
        self.assertNotIn("students_without_parent_phone", keys)

    def test_school_a_issues_do_not_leak_to_school_b(self):
        issues_a = data_quality_checks(school=self.school_a)
        students_no_guardian = next(
            i for i in issues_a if i["key"] == "students_without_guardian"
        )
        self.assertNotIn(
            self.student_clean_b.id,
            students_no_guardian["record_sample_ids"],
            "Tenant isolation: school A's orphan list must not include school B records.",
        )

    def test_summarize_counts(self):
        issues = data_quality_checks(school=self.school_a)
        counts = summarize(issues)
        self.assertEqual(counts["total"], len(issues))
        self.assertGreaterEqual(counts["blocker"], 2)

    def test_data_quality_checks_returns_empty_without_scope(self):
        self.assertEqual(data_quality_checks(school=None), [])
        self.assertEqual(data_quality_checks(), [])

    def test_registry_is_not_empty(self):
        self.assertTrue(len(DATA_QUALITY_CHECKS) >= 3)


class DataQualityCenterViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.school = School.objects.create(name="View School", slug="dq-view", subdomain="dq-view-sub")
        cls.user = User.objects.create_user(
            username="dq_user", email="dq@example.com", password="pwd"
        )
        StudentProfile.objects.create(
            school=cls.school,
            first_name="Lonely",
            last_name="Student",
            is_active=True,
            parent_phone="",
        )

    def setUp(self):
        self.client = Client()

    def test_view_requires_login(self):
        response = self.client.get(reverse("compliance:data_quality_center"))
        self.assertEqual(response.status_code, 302)
