"""
Information Tagging: tests for InformationTag model, StudentProfile.tags, student_tags in nuance, critical-tag signal.
"""
from django.test import TestCase
from django.db import IntegrityError

from apps.people.models import InformationTag, StudentProfile
from apps.schools.models import School
from apps.requests.models import AccessRequest


class InformationTagModelTests(TestCase):
    """InformationTag model: category, is_private, is_critical, unique (school, name)."""

    def setUp(self):
        self.school = School.objects.create(
            name="Tag School",
            slug="tag-school",
            subdomain="tag-school",
            is_active=True,
        )

    def test_create_tag(self):
        tag = InformationTag.objects.create(
            school=self.school,
            name="Early Bird",
            category=InformationTag.Category.FINANCIAL,
            color_hex="#2ecc71",
            is_critical=True,
        )
        self.assertEqual(tag.name, "Early Bird")
        self.assertEqual(tag.category, InformationTag.Category.FINANCIAL)
        self.assertTrue(tag.is_critical)
        self.assertFalse(tag.is_private)

    def test_unique_together_school_name(self):
        InformationTag.objects.create(school=self.school, name="Scholarship")
        with self.assertRaises(IntegrityError):
            InformationTag.objects.create(school=self.school, name="Scholarship")

    def test_str(self):
        tag = InformationTag.objects.create(
            school=self.school,
            name="Asthma",
            category=InformationTag.Category.MEDICAL,
        )
        self.assertIn("Medical", str(tag))
        self.assertIn("Asthma", str(tag))


class StudentTagsAndNuanceContextTests(TestCase):
    """StudentProfile.tags M2M and student_tags in fee_discount context."""

    def setUp(self):
        self.school = School.objects.create(
            name="Nuance School",
            slug="nuance-school",
            subdomain="nuance-school",
            is_active=True,
        )
        self.tag1 = InformationTag.objects.create(
            school=self.school,
            name="Early Bird",
            category=InformationTag.Category.GENERAL,
            is_active=True,
        )
        self.tag2 = InformationTag.objects.create(
            school=self.school,
            name="Scholarship",
            category=InformationTag.Category.FINANCIAL,
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Test",
            last_name="Student",
            student_code="STU001",
            is_active=True,
        )

    def test_student_tags_list(self):
        self.student.tags.add(self.tag1, self.tag2)
        names = list(
            self.student.tags.filter(is_active=True).values_list("name", flat=True)
        )
        self.assertIn("Early Bird", names)
        self.assertIn("Scholarship", names)

    def test_nuance_in_operator_with_student_tags(self):
        from apps.siteconfig.nuance_engine import _safe_eval
        self.student.tags.add(self.tag1)
        student_tags = list(
            self.student.tags.filter(is_active=True).values_list("name", flat=True)
        )
        data = {"student_tags": student_tags, "fee": 100}
        # {"in": ["Early Bird", {"var": "student_tags"}]} -> True
        logic = {"in": ["Early Bird", {"var": "student_tags"}]}
        result = _safe_eval(logic, data)
        self.assertTrue(result)
        logic2 = {"in": ["Not a tag", {"var": "student_tags"}]}
        self.assertFalse(_safe_eval(logic2, data))


class CriticalTagSignalTests(TestCase):
    """When a critical InformationTag is added to a student, AccessRequest is created and optionally assigned."""

    def setUp(self):
        from apps.accounts.models import User
        self.school = School.objects.create(
            name="Signal School",
            slug="signal-school",
            subdomain="signal-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@signal.test",
            email="admin@signal.test",
            password="test",
            role=User.Role.ADMIN,
        )
        from apps.schools.models import SchoolMembership
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Critical",
            last_name="Student",
            student_code="CRIT001",
            is_active=True,
        )
        self.critical_tag = InformationTag.objects.create(
            school=self.school,
            name="Disputed Account",
            category=InformationTag.Category.GENERAL,
            is_critical=True,
            is_active=True,
        )

    def test_adding_critical_tag_creates_access_request(self):
        initial_count = AccessRequest.objects.count()
        self.student.tags.add(self.critical_tag)
        self.assertEqual(AccessRequest.objects.count(), initial_count + 1)
        req = AccessRequest.objects.filter(
            request_type=AccessRequest.RequestType.OTHER,
            details__source="critical_information_tag",
        ).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.details.get("student_id"), self.student.pk)
        self.assertIn("Disputed Account", req.details.get("tags", []))
        self.assertEqual(req.target_object_id, str(self.student.pk))

    def test_adding_non_critical_tag_does_not_create_request(self):
        normal_tag = InformationTag.objects.create(
            school=self.school,
            name="Normal",
            category=InformationTag.Category.GENERAL,
            is_critical=False,
            is_active=True,
        )
        initial_count = AccessRequest.objects.count()
        self.student.tags.add(normal_tag)
        self.assertEqual(AccessRequest.objects.count(), initial_count)
