"""Student one-record aggregation (Student 360, search story)."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.people.views_backend import backend_student_detail
from apps.schools.models import School


class OneRecordDataTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="OR School",
            slug="or-school",
            subdomain="or-school",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Alex",
            last_name="Story",
            student_code="OR-STU-1",
            admission_number="ADM-99",
            is_active=True,
        )

    def test_build_student_one_record_has_profile(self):
        from apps.portal.one_record import build_student_one_record_data

        out = build_student_one_record_data(self.student, self.school)
        self.assertIn("data", out)
        prof = out["data"]["profile"]
        self.assertEqual(prof["first_name"], "Alex")
        self.assertEqual(prof["last_name"], "Story")
        self.assertEqual(prof["student_code"], "OR-STU-1")
        self.assertIn("information_tags", prof)
        self.assertIn("tags", out["data"])
        self.assertIn("tags", out["sections"])

    def test_one_record_includes_assigned_tags(self):
        from apps.people.models import InformationTag
        from apps.portal.one_record import build_student_one_record_data

        tag = InformationTag.objects.create(
            school=self.school,
            name="Scholarship",
            category=InformationTag.Category.FINANCIAL,
            color_hex="#336699",
        )
        self.student.tags.add(tag)
        out = build_student_one_record_data(
            StudentProfile.objects.prefetch_related("tags").get(pk=self.student.pk),
            self.school,
        )
        items = out["data"]["tags"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Scholarship")

    def test_story_preview_lines(self):
        from apps.portal.one_record import build_student_story_preview

        story = build_student_story_preview(self.student, self.school)
        self.assertIn("academic_line", story)
        self.assertIn("finance_line", story)
        self.assertIn("communication_line", story)
        self.assertIn("attendance_line", story)


class BackendStudentDetailViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="360 School",
            slug="360-school",
            subdomain="360-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="360admin",
            password="pw",
            role=User.Role.ADMIN,
        )
        ct = ContentType.objects.get_for_model(StudentProfile)
        perm = Permission.objects.get(content_type=ct, codename="view_studentprofile")
        self.user.user_permissions.add(perm)

        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Sam",
            last_name="Detail",
            student_code="360-1",
            is_active=True,
        )

    def test_student_detail_404_wrong_school(self):
        other = School.objects.create(
            name="Other",
            slug="other-sch",
            subdomain="other-sch",
            is_active=True,
        )
        st2 = StudentProfile.objects.create(
            school=other,
            first_name="X",
            last_name="Y",
            student_code="XY1",
            is_active=True,
        )
        factory = RequestFactory()
        request = factory.get(f"/backend/students/{st2.pk}/")
        request.user = self.user
        request.school = self.school
        with self.assertRaises(Http404):
            backend_student_detail(request, st2.pk)

    def test_student_detail_200(self):
        factory = RequestFactory()
        request = factory.get(f"/backend/students/{self.student.pk}/")
        request.user = self.user
        request.school = self.school
        resp = backend_student_detail(request, self.student.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Student 360", resp.content)
        self.assertIn(b"Sam", resp.content)

    def test_student_detail_portal_tabbed_360_before_admin_fallback(self):
        """1083: tabbed portal 360 is primary; Django admin is Advanced fallback."""
        factory = RequestFactory()
        request = factory.get(f"/backend/students/{self.student.pk}/")
        request.user = self.user
        request.school = self.school
        body = backend_student_detail(request, self.student.pk).content.decode(
            "utf-8", errors="replace"
        )
        p = body.find("Open tabbed 360")
        a = body.find("Advanced/Admin: student row")
        self.assertNotEqual(p, -1, msg="missing tabbed 360 primary link")
        self.assertNotEqual(a, -1, msg="missing admin fallback link")
        self.assertLess(p, a)
