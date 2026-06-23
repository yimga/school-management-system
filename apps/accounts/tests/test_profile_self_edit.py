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
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile

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


class GuardianProfileSelfEditTests(TestCase):
    """Parents/guardians can self-edit their own contact + notification prefs.

    Audit finding: a parent could not edit any of their StudentGuardian contact
    fields (phone, WhatsApp, address, preferred channel) or notification toggles
    — only an admin could, via the backend. A parent holds one link per child;
    the self-edit writes uniformly across every link so contact stays
    consistent. The admin-managed permission fields (can_view_results,
    can_view_finance) must never be exposed or mutated by self-edit.
    """

    def _make_parent(self, username, *, children=1, **link_kwargs):
        parent = User.objects.create_user(
            username=username, password="x", role=User.Role.PARENT
        )
        links = []
        for i in range(children):
            student = StudentProfile.objects.create(
                first_name=f"Kid{i}",
                last_name="Doe",
                student_code=f"{username}-{i}",
            )
            link = StudentGuardian.objects.create(
                guardian_user=parent, student=student, **link_kwargs
            )
            links.append(link)
        return parent, links

    def test_parent_form_exposes_guardian_fields_with_initials(self):
        parent, _ = self._make_parent(
            "gp_parent1",
            phone="111",
            whatsapp_number="222",
            address="12 Rue Test",
            preferred_contact=StudentGuardian.PreferredContact.SMS,
        )
        form = UserProfileEditForm(instance=parent)
        for f in (
            "guardian_phone",
            "guardian_whatsapp",
            "guardian_address",
            "preferred_contact",
            "receives_email",
            "receives_sms",
            "receives_whatsapp",
        ):
            self.assertIn(f, form.fields)
        self.assertEqual(form.fields["guardian_phone"].initial, "111")
        self.assertEqual(form.fields["guardian_whatsapp"].initial, "222")
        self.assertEqual(form.fields["guardian_address"].initial, "12 Rue Test")
        self.assertEqual(
            form.fields["preferred_contact"].initial,
            StudentGuardian.PreferredContact.SMS,
        )

    def test_parent_save_writes_uniformly_across_all_children(self):
        parent, links = self._make_parent("gp_parent2", children=2, phone="old")
        form = UserProfileEditForm(
            {
                "first_name": "Pat",
                "last_name": "Doe",
                "email": "",
                "guardian_phone": "+237 6 11 11 11 11",
                "guardian_whatsapp": "+237 6 22 22 22 22",
                "guardian_address": "New address",
                "preferred_contact": StudentGuardian.PreferredContact.WHATSAPP,
                "receives_sms": "on",
                "receives_whatsapp": "on",
                # receives_email intentionally absent -> should become False
            },
            instance=parent,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        for link in links:
            link.refresh_from_db()
            self.assertEqual(link.phone, "+237 6 11 11 11 11")
            self.assertEqual(link.whatsapp_number, "+237 6 22 22 22 22")
            self.assertEqual(link.address, "New address")
            self.assertEqual(
                link.preferred_contact, StudentGuardian.PreferredContact.WHATSAPP
            )
            self.assertFalse(link.receives_email)
            self.assertTrue(link.receives_sms)
            self.assertTrue(link.receives_whatsapp)

    def test_parent_self_edit_never_touches_permission_fields(self):
        parent, links = self._make_parent("gp_parent3", phone="x")
        link = links[0]
        # Admin-set permissions; self-edit must leave them exactly as-is.
        link.can_view_results = True
        link.can_view_finance = True
        link.save(update_fields=["can_view_results", "can_view_finance"])

        form = UserProfileEditForm(instance=parent)
        self.assertNotIn("can_view_results", form.fields)
        self.assertNotIn("can_view_finance", form.fields)

        bound = UserProfileEditForm(
            {
                "first_name": "Pat",
                "last_name": "Doe",
                "email": "",
                "guardian_phone": "999",
                "preferred_contact": StudentGuardian.PreferredContact.EMAIL,
            },
            instance=parent,
        )
        self.assertTrue(bound.is_valid(), bound.errors)
        bound.save()
        link.refresh_from_db()
        self.assertEqual(link.phone, "999")
        self.assertTrue(link.can_view_finance)
        self.assertTrue(link.can_view_results)

    def test_non_parent_non_teacher_has_no_extra_fields(self):
        user = User.objects.create_user(
            username="gp_student", password="x", role=User.Role.STUDENT
        )
        form = UserProfileEditForm(instance=user)
        self.assertNotIn("guardian_phone", form.fields)
        self.assertNotIn("contact_phone", form.fields)

    def test_dual_role_teacher_guardian_gets_both_blocks(self):
        # A teacher who is also a guardian (allowed by StudentGuardian.clean)
        # should self-edit both their staff phone and their guardian contact.
        user = User.objects.create_user(
            username="gp_dual", password="x", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=user, phone="staff-000")
        student = StudentProfile.objects.create(
            first_name="Kid", last_name="Dual", student_code="gp_dual-0"
        )
        StudentGuardian.objects.create(guardian_user=user, student=student, phone="g-000")
        form = UserProfileEditForm(instance=user)
        self.assertIn("contact_phone", form.fields)
        self.assertIn("guardian_phone", form.fields)
