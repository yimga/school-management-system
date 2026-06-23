"""Profiles wiring: teachers can self-edit their contact phone.

Audit finding: self-service profile editing only touched the base User (name,
email, photo); role-profile fields were locked to admins. This lets a teacher
update their own contact phone (TeacherProfile.phone) — a safe field — while
sensitive role data (pay, permissions, staff_id) stays admin-managed and is
never exposed in the self-edit form.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms import UserProfileEditForm
from apps.people.models import TeacherProfile

User = get_user_model()


class TeacherProfileSelfEditTests(TestCase):
    def test_teacher_form_exposes_contact_phone(self):
        user = User.objects.create_user(
            username="tp_teacher", password="x", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=user, phone="000")
        form = UserProfileEditForm(instance=user)
        self.assertIn("contact_phone", form.fields)
        self.assertEqual(form.fields["contact_phone"].initial, "000")

    def test_teacher_can_save_new_phone_to_profile(self):
        user = User.objects.create_user(
            username="tp_teacher2", password="x", role=User.Role.TEACHER
        )
        profile = TeacherProfile.objects.create(user=user, phone="old")
        form = UserProfileEditForm(
            {
                "first_name": "Tee",
                "last_name": "Cher",
                "email": "",
                "contact_phone": "+237 6 00 00 00 00",
            },
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        profile.refresh_from_db()
        self.assertEqual(profile.phone, "+237 6 00 00 00 00")

    def test_non_teacher_has_no_contact_phone_field(self):
        user = User.objects.create_user(
            username="tp_parent", password="x", role=User.Role.PARENT
        )
        form = UserProfileEditForm(instance=user)
        self.assertNotIn(
            "contact_phone",
            form.fields,
            "only teachers have a self-editable role-profile field today",
        )

    def test_save_does_not_expose_sensitive_role_fields(self):
        # The form must never let a user touch pay/permissions via self-edit.
        user = User.objects.create_user(
            username="tp_teacher3", password="x", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=user, phone="000")
        form = UserProfileEditForm(instance=user)
        for sensitive in ("salary_amount", "pay_scale", "pay_grade", "staff_id"):
            self.assertNotIn(sensitive, form.fields)
