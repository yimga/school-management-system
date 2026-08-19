"""Guardian directory promote + parent/teacher first-login activation (2026-08-18)."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.email_delivery_policy import (
    is_deliverable_email,
    synthetic_unclaimed_email,
)
from apps.accounts.models import User
from apps.migration_cloud.guardian_directory import (
    ensure_school_membership,
    promote_guardian_directory_link,
)
from apps.migration_cloud.people_activation import (
    activation_snapshot,
    handover_csv_response,
    invite_unactivated_parents,
)
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership


class EmailDeliveryPolicyTests(SimpleTestCase):
    def test_real_mailbox_is_deliverable(self):
        self.assertTrue(is_deliverable_email("parent@school.cm"))

    def test_synthetic_unclaimed_is_not_deliverable(self):
        addr = synthetic_unclaimed_email("school|phone|andoh")
        self.assertTrue(addr.endswith("@unclaimed.invalid"))
        self.assertFalse(is_deliverable_email(addr))

    def test_blank_is_not_deliverable(self):
        self.assertFalse(is_deliverable_email(""))
        self.assertFalse(is_deliverable_email("not-an-email"))


class GuardianDirectoryPromoteTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Directory School", subdomain="dir-promote", country_code="CM"
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Lovelace"
        )

    def test_promotes_name_into_guardian_list_with_unusable_password(self):
        link = promote_guardian_directory_link(
            student=self.student,
            name="Andoh Julius",
            phone="+237690000001",
            school=self.school,
        )
        self.assertIsNotNone(link)
        self.assertEqual(link.student_id, self.student.pk)
        self.assertEqual(link.guardian_user.role, User.Role.PARENT)
        self.assertFalse(link.guardian_user.has_usable_password())
        self.assertTrue(
            StudentGuardian.objects.filter(
                student__school=self.school, guardian_user=link.guardian_user
            ).exists()
        )
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=self.school, user=link.guardian_user, role=User.Role.PARENT
            ).exists()
        )

    def test_same_parent_phone_reuses_one_user_across_siblings(self):
        sibling = StudentProfile.objects.create(
            school=self.school, first_name="Alan", last_name="Turing"
        )
        first = promote_guardian_directory_link(
            student=self.student,
            name="Andoh Julius",
            phone="+237690000001",
            school=self.school,
        )
        second = promote_guardian_directory_link(
            student=sibling,
            name="Andoh Julius",
            phone="+237690000001",
            school=self.school,
        )
        self.assertEqual(first.guardian_user_id, second.guardian_user_id)
        self.assertEqual(
            StudentGuardian.objects.filter(guardian_user=first.guardian_user).count(),
            2,
        )

    def test_idempotent_on_the_same_student(self):
        first = promote_guardian_directory_link(
            student=self.student, name="Andoh Julius", school=self.school
        )
        second = promote_guardian_directory_link(
            student=self.student, name="Andoh Julius", school=self.school
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            StudentGuardian.objects.filter(student=self.student).count(), 1
        )


class PeopleActivationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Activate School", subdomain="act-people", country_code="CM"
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Lovelace"
        )
        self.link = promote_guardian_directory_link(
            student=self.student,
            name="Andoh Julius",
            email="andoh@example.cm",
            school=self.school,
        )
        teacher_user = User.objects.create_user(
            username="t.activate",
            email="teacher@example.cm",
            first_name="Jane",
            last_name="Doe",
            role=User.Role.TEACHER,
        )
        teacher_user.set_unusable_password()
        teacher_user.save()
        TeacherProfile.objects.create(school=self.school, user=teacher_user, staff_id="T1")
        ensure_school_membership(
            user=teacher_user, school=self.school, role=User.Role.TEACHER
        )
        self.teacher = teacher_user

    def test_snapshot_counts_unactivated_parents_and_staff(self):
        snap = activation_snapshot(self.school)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["parent_count"], 1)
        self.assertEqual(snap["staff_count"], 1)
        self.assertEqual(snap["parent_inviteable"], 1)
        self.assertEqual(snap["staff_inviteable"], 1)

    def test_invite_parents_queues_mail(self):
        with mock.patch("apps.schoolops.email_delivery.send_transactional") as st:
            out = invite_unactivated_parents(school=self.school)
        self.assertEqual(out["sent"], 1)
        st.assert_called_once()

    def test_invite_skips_synthetic_email(self):
        self.link.guardian_user.email = synthetic_unclaimed_email("x")
        self.link.guardian_user.save(update_fields=["email"])
        with mock.patch("apps.schoolops.email_delivery.send_transactional") as st:
            out = invite_unactivated_parents(school=self.school)
        self.assertEqual(out["sent"], 0)
        self.assertEqual(out["skipped"], 1)
        st.assert_not_called()

    def test_handover_csv_forces_first_login_profile(self):
        response = handover_csv_response(school=self.school, kind="staff")
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8")
        self.assertIn("temporary_password", body)
        self.assertIn(self.teacher.username, body)
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.has_usable_password())
        self.assertTrue(self.teacher.requires_password_change)
        self.assertFalse(self.teacher.profile_setup_completed)

    def test_mail_failure_downloads_remainder_csv(self):
        from apps.migration_cloud.people_activation import activate_mail_then_handover

        with mock.patch(
            "apps.schoolops.email_delivery.send_transactional",
            side_effect=RuntimeError("smtp down"),
        ):
            response = activate_mail_then_handover(school=self.school, kind="staff")
        self.assertIsNotNone(response)
        body = response.content.decode("utf-8")
        self.assertIn(self.teacher.username, body)
        self.assertIn("temporary_password", body)
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.has_usable_password())

    def test_successful_mail_does_not_mint_csv_password(self):
        from apps.migration_cloud.people_activation import activate_mail_then_handover

        with mock.patch("apps.schoolops.email_delivery.send_transactional") as st:
            response = activate_mail_then_handover(school=self.school, kind="staff")
        self.assertIsNone(response)
        st.assert_called_once()
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.has_usable_password())


class StaffSetupInviteTests(SimpleTestCase):
    def test_build_link_contains_staff_setup_route(self):
        from apps.accounts.guardian_invite import build_staff_setup_link

        UserModel = get_user_model()
        user = UserModel(pk=9, email="t@example.cm", password="!unusable")
        link = build_staff_setup_link(user, base_url="https://x.test")
        self.assertIn("/staff-setup/", link)
