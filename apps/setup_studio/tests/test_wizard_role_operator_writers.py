"""Role + operator wizard domain writer tests (batch 7)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.registries.models import CountryRegistry
from apps.schools.models import School, SchoolDomain
from apps.setup_studio.wizard_resolvers_domain import (
    write_parent_contact_preferences_step,
    write_parent_payment_setup_step,
    write_password_rotation_step,
    write_student_course_selection_step,
    write_teacher_attendance_intake_step,
    write_teacher_gradebook_setup_step,
)
from apps.setup_studio.wizard_resolvers_operator import (
    write_account_migration_step,
    write_custom_domain_step,
    write_parent_link_child_step,
    write_student_self_onboarding_step,
    write_teacher_self_onboarding_step,
)


class RoleWizardWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Role School",
            slug="role-school",
            subdomain="role-school",
            country_code="CM",
            is_active=True,
        )
        User = get_user_model()
        self.parent = User.objects.create_user(
            username="parent-role",
            password="x",
            role=User.Role.PARENT,
        )
        self.student_user = User.objects.create_user(
            username="student-role",
            password="x",
            role=User.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            admission_number="ADM-R1",
            first_name="Kid",
            last_name="One",
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            receives_email=False,
            receives_sms=False,
        )

    def test_gradebook_and_course_selection(self):
        write_teacher_gradebook_setup_step(
            school=self.school,
            wizard_key="teacher_gradebook_setup",
            step_key="select_class",
            payload={"value": "42"},
            actor_user_id=99,
        )
        write_student_course_selection_step(
            school=self.school,
            wizard_key="student_course_selection",
            step_key="confirm",
            payload={"value": True},
            actor_user_id=self.student_user.pk,
        )
        self.school.refresh_from_db()
        role = (self.school.settings or {}).get("role_wizards", {})
        self.assertEqual(
            role["teacher_gradebook_setup"]["users"]["99"]["select_class"]["value"],
            "42",
        )
        self.assertIn(
            str(self.student_user.pk),
            (self.school.settings or {}).get("student_course_requests", {}),
        )

    def test_parent_contact_channels_update_guardian(self):
        write_parent_contact_preferences_step(
            school=self.school,
            wizard_key="parent_contact_preferences",
            step_key="channels",
            payload={"value": ["email", "sms"]},
            actor_user_id=self.parent.pk,
        )
        link = StudentGuardian.objects.get(guardian_user=self.parent, student=self.student)
        self.assertTrue(link.receives_email)
        self.assertTrue(link.receives_sms)

    def test_teacher_attendance_and_parent_payment(self):
        write_teacher_attendance_intake_step(
            school=self.school,
            wizard_key="teacher_attendance_intake",
            step_key="default_mode",
            payload={"value": "tap_grid"},
            actor_user_id=88,
        )
        write_parent_payment_setup_step(
            school=self.school,
            wizard_key="parent_payment_setup",
            step_key="preferred_method",
            payload={
                "value": "mobile_money",
                "card_number": "4111111111111111",
                "card_cvv": "123",
            },
            actor_user_id=self.parent.pk,
        )
        self.school.refresh_from_db()
        role = (self.school.settings or {}).get("role_wizards", {})
        self.assertEqual(
            role["teacher_attendance_intake"]["users"]["88"]["default_mode"]["value"],
            "tap_grid",
        )
        pay_row = (
            (self.school.settings or {})
            .get("parent_payment_setup", {})
            .get("users", {})
            .get(str(self.parent.pk), {})
            .get("preferred_method", {})
        )
        self.assertEqual(pay_row.get("value"), "mobile_money")
        self.assertNotIn("card_number", pay_row)
        self.assertNotIn("card_cvv", pay_row)


class AccountMigrationOperatorWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Migrate School",
            slug="migrate-school",
            subdomain="migrate-school",
            country_code="CM",
            is_active=True,
        )
        from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle, SlaTier

        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            label="Account migration bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            sla_tier=SlaTier.SMALL,
            status=BundleStatus.PENDING,
            size_summary={"worker_log": []},
        )

    def test_select_source_review_mapping_and_kick_off(self):
        write_account_migration_step(
            school=self.school,
            wizard_key="account_migration",
            step_key="select_source",
            payload={"value": "powerschool"},
            actor_user_id=1,
        )
        write_account_migration_step(
            school=self.school,
            wizard_key="account_migration",
            step_key="review_mapping",
            payload={"mapping": {"Student ID": "students.external_id"}},
            actor_user_id=1,
        )
        write_account_migration_step(
            school=self.school,
            wizard_key="account_migration",
            step_key="kick_off",
            payload={"source": "powerschool"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        self.bundle.refresh_from_db()
        mc = (self.school.settings or {}).get("migration_cloud", {})
        self.assertEqual(mc.get("wizard_source"), "powerschool")
        self.assertEqual(
            mc.get("field_vector_mapping", {}).get("Student ID"),
            "students.external_id",
        )
        summary = self.bundle.size_summary or {}
        self.assertIn("field_vector_mapping", summary)
        wizards = (self.school.settings or {}).get("wizards", {})
        self.assertIn("account_migration", wizards)
        self.assertTrue(wizards["account_migration"].get("bundle_id"))


class ParentLinkChildOperatorWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Link School",
            slug="link-school",
            subdomain="link-school",
            country_code="CM",
            is_active=True,
        )
        User = get_user_model()
        self.parent = User.objects.create_user(
            username="parent-link",
            password="x",
            role=User.Role.PARENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            admission_number="ADM-LINK-1",
            first_name="Link",
            last_name="Child",
        )

    def test_confirm_link_creates_guardian_and_redacts_admission_in_cockpit(self):
        write_parent_link_child_step(
            school=self.school,
            wizard_key="parent_link_child",
            step_key="confirm_link",
            payload={
                "admission_number": "ADM-LINK-1",
                "relationship": "mother",
                "preferred_contact": "email",
            },
            actor_user_id=self.parent.pk,
        )
        self.assertTrue(
            StudentGuardian.objects.filter(
                guardian_user=self.parent,
                student=self.student,
            ).exists()
        )
        self.school.refresh_from_db()
        cockpit = (self.school.settings or {}).get("wizards", {}).get("parent_link_child", {}).get("confirm_link", {})
        self.assertNotIn("admission_number", cockpit)
        self.assertIn("admission_number_hash", cockpit)


class CustomDomainOperatorWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Domain School",
            slug="domain-school",
            subdomain="domain-school",
            country_code="US",
            is_active=True,
        )

    def test_domain_entry_schedules_dns_check(self):
        write_custom_domain_step(
            school=self.school,
            wizard_key="custom_domain_setup",
            step_key="domain_entry",
            payload={"value": "portal.example.edu"},
            actor_user_id=1,
        )
        self.assertTrue(
            SchoolDomain.objects.filter(school=self.school, domain="portal.example.edu").exists()
        )


class SelfOnboardingOperatorWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Onboard School",
            slug="onboard-school",
            subdomain="onboard-school",
            country_code="CM",
            is_active=True,
        )

    def test_teacher_self_onboarding_strips_password_and_creates_on_profile_photo(self):
        write_teacher_self_onboarding_step(
            school=self.school,
            wizard_key="teacher_self_onboarding",
            step_key="basic_information",
            payload={
                "first_name": "Tee",
                "last_name": "Cher",
                "email": "teacher-onboard@example.com",
                "password1": "Secret-123!",
                "password2": "Secret-123!",
            },
            actor_user_id=None,
        )
        self.school.refresh_from_db()
        basic = (self.school.settings or {}).get("wizards", {}).get("teacher_self_onboarding", {}).get("basic_information", {})
        self.assertEqual(basic.get("email"), "teacher-onboard@example.com")
        self.assertNotIn("password1", basic)
        self.assertNotIn("password2", basic)

        write_teacher_self_onboarding_step(
            school=self.school,
            wizard_key="teacher_self_onboarding",
            step_key="profile_photo",
            payload={
                "email": "teacher-onboard@example.com",
                "first_name": "Tee",
                "last_name": "Cher",
                "phone": "555-0100",
            },
            actor_user_id=None,
        )
        user = User.objects.get(email="teacher-onboard@example.com")
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertTrue(TeacherProfile.objects.filter(user=user, school=self.school).exists())

    def test_student_self_onboarding_hashes_dob_and_creates_on_profile_photo(self):
        write_student_self_onboarding_step(
            school=self.school,
            wizard_key="student_self_onboarding",
            step_key="identity",
            payload={
                "first_name": "Stu",
                "last_name": "Dent",
                "date_of_birth": "2010-05-15",
                "password": "Secret-123!",
            },
            actor_user_id=None,
        )
        self.school.refresh_from_db()
        identity = (
            (self.school.settings or {})
            .get("wizards", {})
            .get("student_self_onboarding", {})
            .get("identity", {})
        )
        self.assertNotIn("date_of_birth", identity)
        self.assertNotIn("password", identity)
        self.assertIn("date_of_birth_hash", identity)

        write_student_self_onboarding_step(
            school=self.school,
            wizard_key="student_self_onboarding",
            step_key="profile_photo",
            payload={"first_name": "Stu", "last_name": "Dent"},
            actor_user_id=None,
        )
        self.assertTrue(
            StudentProfile.objects.filter(
                school=self.school,
                first_name="Stu",
                last_name="Dent",
            ).exists()
        )


class PasswordRotationWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Rotate School",
            slug="rotate-school",
            subdomain="rotate-school",
            country_code="CM",
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(
            username="rotate-user",
            password="OldPass-2025!",
            role=User.Role.TEACHER,
        )

    def test_confirm_rotates_password_without_persisting_secrets(self):
        write_password_rotation_step(
            school=self.school,
            wizard_key="password_rotation",
            step_key="confirm",
            payload={
                "new_password": "Str0ng-Passw0rd-2026!",
                "confirm_password": "Str0ng-Passw0rd-2026!",
                "verify_identity": "rotate-user",
            },
            actor_user_id=self.user.pk,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ng-Passw0rd-2026!"))
        self.school.refresh_from_db()
        cockpit = (self.school.settings or {}).get("wizards", {}).get("password_rotation", {}).get("confirm", {})
        self.assertNotIn("new_password", cockpit)
        self.assertNotIn("confirm_password", cockpit)
        self.assertIn("verify_identity_hash", cockpit)
