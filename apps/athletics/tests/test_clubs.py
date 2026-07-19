"""Metric 13 — extracurricular clubs (create / enroll / waitlist / withdraw)."""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccessRole, Permission
from apps.athletics.models import Club, ClubCategory, ClubMembership
from apps.athletics.services.clubs import (
    ClubCapacityError,
    assign_advisor,
    create_club,
    enroll_student,
    withdraw_member,
)
from apps.athletics.tests.base import AthleticsFixtureMixin, BaseAthleticsTestCase
from apps.athletics.views.clubs import admin_club_detail, admin_clubs
from apps.people.models import StudentProfile

User = get_user_model()


def _grant(user, *codes):
    role, _ = AccessRole.objects.get_or_create(
        code="ATHLETICS_CLUBS", defaults={"name": "Clubs", "description": "x"}
    )
    for code in codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"name": code, "description": code}
        )
        role.permissions.add(perm)
    user.roles.add(role)


class ClubServiceTests(AthleticsFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self.build_tenant("club")

    def test_create_club_derives_slug(self):
        club = create_club(
            school=self.fx.school,
            name="Debate Society",
            category=ClubCategory.ACADEMIC,
            academic_year=self.fx.year,
        )
        self.assertEqual(club.slug, "debate-society")
        self.assertEqual(club.status, Club.Status.FORMING)
        self.assertEqual(club.school_id, self.fx.school.id)

    def test_enroll_active_then_waitlist_at_capacity(self):
        club = create_club(
            school=self.fx.school,
            name="Robotics",
            category=ClubCategory.STEM,
            capacity=1,
            status=Club.Status.ACTIVE,
        )
        first = enroll_student(club=club, student=self.fx.student)
        self.assertEqual(first.status, ClubMembership.Status.ACTIVE)

        extra = StudentProfile.objects.create(
            school=self.fx.school,
            first_name="Extra",
            last_name="Member",
            student_code="STD-club-2",
            admission_number="ADM-club-2",
            academic_year=self.fx.year,
            classroom=self.fx.classroom,
            specialty=self.fx.specialty,
        )
        second = enroll_student(club=club, student=extra)
        self.assertEqual(second.status, ClubMembership.Status.WAITLIST)

    def test_force_active_at_capacity_raises(self):
        club = create_club(
            school=self.fx.school, name="Choir", capacity=1, status=Club.Status.ACTIVE
        )
        enroll_student(club=club, student=self.fx.student)
        extra = StudentProfile.objects.create(
            school=self.fx.school,
            first_name="Overflow",
            last_name="Kid",
            student_code="STD-club-3",
            admission_number="ADM-club-3",
            academic_year=self.fx.year,
            classroom=self.fx.classroom,
            specialty=self.fx.specialty,
        )
        with self.assertRaises(ClubCapacityError):
            enroll_student(club=club, student=extra, force_active=True)

    def test_enroll_idempotent_for_same_student(self):
        club = create_club(school=self.fx.school, name="Chess")
        a = enroll_student(club=club, student=self.fx.student)
        b = enroll_student(club=club, student=self.fx.student)
        self.assertEqual(a.pk, b.pk)

    def test_withdraw_marks_left(self):
        club = create_club(school=self.fx.school, name="Service Club")
        membership = enroll_student(club=club, student=self.fx.student)
        withdraw_member(membership=membership)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ClubMembership.Status.LEFT)
        self.assertIsNotNone(membership.left_at)

    def test_assign_advisor(self):
        club = create_club(school=self.fx.school, name="Newspaper")
        assignment = assign_advisor(club=club, advisor=self.fx.teacher_user)
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.advisor_id, self.fx.teacher_user.id)


class ClubAdminViewTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()

    def _prep(self, request):
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request._messages = FallbackStorage(request)
        request.urlconf = "config.tenant_urls"
        return request

    def _admin_user(self, username="club_admin"):
        user = User.objects.create_user(username=username, password="pass123")
        if hasattr(user, "role"):
            user.role = User.Role.ADMIN
            user.save(update_fields=["role"])
        _grant(user, "athletics.view", "athletics.manage")
        return user

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_admin_clubs_200_with_manage(self):
        user = self._admin_user()
        request = self.rf.get("/athletics/admin/clubs/")
        request.user = user
        request.school = self.fx.school
        self._prep(request)
        resp = admin_clubs(request)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Clubs", content)
        self.assertIn("Create a club", content)

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_admin_club_detail_shows_roster(self):
        user = self._admin_user("club_detail_admin")
        club = create_club(
            school=self.fx.school,
            name="Drama Club",
            category=ClubCategory.ARTS,
            status=Club.Status.ACTIVE,
        )
        enroll_student(club=club, student=self.fx.student, role_title="Lead")
        request = self.rf.get(f"/athletics/admin/clubs/{club.id}/")
        request.user = user
        request.school = self.fx.school
        self._prep(request)
        resp = admin_club_detail(request, club_id=club.id)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Drama Club", content)
        self.assertIn("Lead", content)

    def test_view_only_cannot_post_create(self):
        user = User.objects.create_user(username="viewer", password="pass123")
        _grant(user, "athletics.view")
        request = self.rf.post(
            "/athletics/admin/clubs/",
            {"name": "Should Fail", "category": "other", "capacity": 10, "status": "forming"},
        )
        request.user = user
        request.school = self.fx.school
        self._prep(request)
        with self.assertRaises(PermissionDenied):
            admin_clubs(request)

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_url_names_registered(self):
        self.assertEqual(reverse("athletics:admin_clubs"), "/athletics/admin/clubs/")
        club = create_club(school=self.fx.school, name="URL Club")
        self.assertEqual(
            reverse("athletics:admin_club_detail", kwargs={"club_id": club.id}),
            f"/athletics/admin/clubs/{club.id}/",
        )
