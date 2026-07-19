"""Metric #13 — family club surface on athletics my-team."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.athletics.models import Club, ClubCategory, ClubMembership
from apps.athletics.services.clubs import create_club, enroll_student
from apps.athletics.tests.base import AthleticsFixtureMixin
from apps.athletics.views.family import family_my_team
from apps.people.models import StudentGuardian
from apps.schools.models import SchoolMembership

User = get_user_model()

_FAMILY_PATH = "/athletics/my-team/"


@override_settings(ROOT_URLCONF="config.tenant_urls")
class FamilyClubsTests(AthleticsFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self.build_tenant("fam")
        self.club = create_club(
            school=self.fx.school,
            name="Chess Club",
            category=ClubCategory.ACADEMIC,
            academic_year=self.fx.year,
            status=Club.Status.ACTIVE,
        )
        self.parent = User.objects.create_user(
            username="par_fam_clubs",
            email="par@fam.clubs.test",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=self.parent, school=self.fx.school, role="PARENT"
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.fx.student,
            can_view_results=True,
        )
        self.factory = RequestFactory()

    def _req(self, method="get", data=None):
        if method == "post":
            req = self.factory.post(_FAMILY_PATH, data or {})
        else:
            req = self.factory.get(_FAMILY_PATH)
        req.user = self.parent
        req.school = self.fx.school
        SessionMiddleware(lambda x: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_parent_sees_child_club_membership(self):
        enroll_student(club=self.club, student=self.fx.student)
        resp = family_my_team(self._req())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Chess Club", body)
        self.assertIn(self.fx.student.last_name, body)

    def test_parent_can_enroll_child(self):
        resp = family_my_team(
            self._req(
                "post",
                {
                    "intent": "enroll_club",
                    "club_id": str(self.club.pk),
                    "student_id": str(self.fx.student.pk),
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            ClubMembership.objects.filter(
                club=self.club,
                student=self.fx.student,
                status=ClubMembership.Status.ACTIVE,
            ).exists()
        )

    def test_parent_cannot_enroll_other_school_child(self):
        other = self.build_tenant("oth")
        other_club = create_club(
            school=other.school,
            name="Other Club",
            status=Club.Status.ACTIVE,
            academic_year=other.year,
        )
        resp = family_my_team(
            self._req(
                "post",
                {
                    "intent": "enroll_club",
                    "club_id": str(other_club.pk),
                    "student_id": str(other.student.pk),
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            ClubMembership.objects.filter(
                club=other_club, student=other.student
            ).exists()
        )
