"""Seal: the 4 wizard-delegation services (previously phantom) actually perform
their terminal actions — guardian link, teacher create, student create, password
rotation."""
from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.services_link_child import link_guardian_to_student
from apps.accounts.services_password_rotation import perform_password_rotation
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.portal.services_student_onboarding import create_student_from_wizard
from apps.portal.services_teacher_onboarding import create_teacher_from_wizard
from apps.schools.models import School


def _school():
    return School.objects.create(name="svc-school", slug="svc-school", subdomain="svc-school", is_active=True)


class GuardianLinkServiceTests(TestCase):
    def setUp(self):
        self.school = _school()
        self.parent = User.objects.create_user(
            username="p@x.io", email="p@x.io", role=User.Role.PARENT
        )
        self.student = StudentProfile.objects.create(
            first_name="Kid", last_name="One", school=self.school,
            admission_number="ADM-1", status=StudentProfile.Status.NEW,
        )

    def test_links_then_idempotent(self):
        r1 = link_guardian_to_student(
            school=self.school, actor_user_id=self.parent.pk,
            admission_number="ADM-1", relationship="mother", preferred_contact="whatsapp",
        )
        self.assertTrue(r1["ok"] and r1["created"])
        self.assertTrue(
            StudentGuardian.objects.filter(guardian_user=self.parent, student=self.student).exists()
        )
        r2 = link_guardian_to_student(
            school=self.school, actor_user_id=self.parent.pk,
            admission_number="ADM-1", relationship="mother", preferred_contact="whatsapp",
        )
        self.assertTrue(r2["ok"] and r2["already_linked"])

    def test_unknown_admission(self):
        r = link_guardian_to_student(
            school=self.school, actor_user_id=self.parent.pk,
            admission_number="NOPE", relationship="father", preferred_contact="email",
        )
        self.assertEqual(r["error"], "student_not_found")

    def test_non_guardian_role_rejected(self):
        student_user = User.objects.create_user(
            username="s@x.io", email="s@x.io", role=User.Role.STUDENT
        )
        r = link_guardian_to_student(
            school=self.school, actor_user_id=student_user.pk,
            admission_number="ADM-1", relationship="other", preferred_contact="email",
        )
        self.assertEqual(r["error"], "actor_not_guardian_role")


class TeacherStudentOnboardingServiceTests(TestCase):
    def setUp(self):
        self.school = _school()

    def test_create_teacher(self):
        r = create_teacher_from_wizard(
            school=self.school, actor_user_id=None,
            wizard_payload={"email": "t@x.io", "first_name": "Tee", "last_name": "Cher", "phone": "123"},
        )
        self.assertTrue(r["ok"])
        user = User.objects.get(pk=r["user_id"])
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertTrue(TeacherProfile.objects.filter(user=user, school=self.school).exists())

    def test_duplicate_teacher_email(self):
        User.objects.create_user(username="dup@x.io", email="dup@x.io", role=User.Role.TEACHER)
        r = create_teacher_from_wizard(
            school=self.school, actor_user_id=None,
            wizard_payload={"email": "dup@x.io", "first_name": "A", "last_name": "B"},
        )
        self.assertEqual(r["error"], "email_exists")

    def test_create_student(self):
        r = create_student_from_wizard(
            school=self.school, actor_user_id=None,
            wizard_payload={"first_name": "Stu", "last_name": "Dent"},
        )
        self.assertTrue(r["ok"])
        self.assertTrue(StudentProfile.objects.filter(pk=r["student_profile_id"]).exists())


class PasswordRotationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u@x.io", email="u@x.io", role=User.Role.TEACHER)
        self.user.set_password("OldPass-2025!")
        self.user.save()

    def test_rotates_password(self):
        r = perform_password_rotation(
            actor_user_id=self.user.pk,
            payload={"new_password": "Str0ng-Passw0rd-2026!", "confirm_password": "Str0ng-Passw0rd-2026!"},
        )
        self.assertTrue(r["ok"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ng-Passw0rd-2026!"))

    def test_mismatch_rejected(self):
        r = perform_password_rotation(
            actor_user_id=self.user.pk,
            payload={"new_password": "Str0ng-Passw0rd-2026!", "confirm_password": "different"},
        )
        self.assertEqual(r["error"], "password_mismatch")

    def test_weak_password_rejected(self):
        r = perform_password_rotation(
            actor_user_id=self.user.pk,
            payload={"new_password": "123", "confirm_password": "123"},
        )
        self.assertEqual(r["error"], "weak_password")
