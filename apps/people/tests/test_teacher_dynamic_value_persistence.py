"""Regression: the Teacher CREATE VIEW persists dynamic custom-field VALUES.

Bug (audit metric #5, LEG 1 — active data-loss): ``TeacherCreateForm.__init__``
ATTACHED tenant EAV fields (e.g. the Gulf residency-permit reference), so they
rendered on the form, but ``backend_teacher_create`` built the form with NO
``school=`` (so only platform-wide definitions rendered) AND never called
``save_dynamic_fields_for_model`` after saving the teacher — unlike the student
path. So a teacher custom field the operator filled in was silently dropped.

The fix resolves ``school`` from the request, passes it to the form, and wires
``save_dynamic_fields_for_model(..., model=TeacherProfile, instance=<teacher>,
school=<school>)`` into the successful-save path (inside ``transaction.atomic``).

These DB-backed tests POST the create form with a value for a teacher-scoped
custom field and assert a tenant-scoped ``DynamicFieldValue`` row persists for
the new teacher.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import unwrap_value
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


class TeacherCreateViewDynamicValuePersistenceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Teacher Value School",
            slug="teacher-value-school",
            subdomain="teacher-value-school",
            is_active=True,
        )
        # Superuser bypasses the ``people.add_teacherprofile`` permission gate;
        # the SchoolMembership lets ``resolve_request_school`` pin the tenant when
        # no subdomain middleware runs under the test client.
        self.user = User.objects.create_superuser(
            username="admin@teacher-value.test",
            email="admin@teacher-value.test",
            password="test-pass-123",
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        # HR-defined custom field, correctly keyed to the TeacherProfile entity.
        DynamicFieldDefinition.objects.create(
            entity_type="people.teacherprofile",
            field_key="iqama_or_residency",
            label="Residency permit reference",
            data_type="string",
            school=self.school,
            is_active=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:backend_teacher_create")

    def _post_payload(self, **overrides):
        payload = {
            "email": "new.teacher@example.com",
            "username": "new.teacher",
            "password": "Temp-Pass-123",
            "staff_id": "STAFF-EAV-1",
            "dyn_iqama_or_residency": "RP-2026-004417",
        }
        payload.update(overrides)
        return payload

    def test_create_view_persists_dynamic_field_value(self):
        resp = self.client.post(self.url, self._post_payload())
        self.assertIn(resp.status_code, (302, 303), msg=resp.content[:500])

        teacher = TeacherProfile.objects.get(user__email="new.teacher@example.com")

        value = DynamicFieldValue.objects.filter(
            entity_type="people.teacherprofile",
            entity_id=str(teacher.pk),
            field_key="iqama_or_residency",
            school=self.school,
        ).first()
        self.assertIsNotNone(
            value,
            msg=(
                "Teacher custom-field VALUE was not persisted — the create view "
                "did not call save_dynamic_fields_for_model (metric #5 LEG 1)."
            ),
        )
        self.assertEqual(unwrap_value(value.value_json), "RP-2026-004417")

    def test_persisted_value_is_tenant_scoped(self):
        other_school = School.objects.create(
            name="Other Teacher School",
            slug="other-teacher-school",
            subdomain="other-teacher-school",
            is_active=True,
        )
        self.client.post(self.url, self._post_payload())
        teacher = TeacherProfile.objects.get(user__email="new.teacher@example.com")
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                entity_id=str(teacher.pk),
                field_key="iqama_or_residency",
                school=self.school,
            ).exists()
        )
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_id=str(teacher.pk),
                field_key="iqama_or_residency",
                school=other_school,
            ).exists()
        )
