"""M5 RENDER leg: dynamic EAV inputs must be EMITTED on the student create form.

Bug (audit metric #5): ``StudentCreateForm`` attaches ``dyn_*`` fields via
``attach_dynamic_fields``, but ``templates/people/backend_student_create.html``
hand-rendered only the static model fields — the dynamic inputs were never
emitted. So a real browser never submitted them and
``save_dynamic_fields_from_form`` silently persisted nothing. The existing
save-leg tests passed only because they hand-BUILT the POST dict (``dyn_...``
keys), bypassing the missing input entirely. These tests GET the rendered form
and assert the input is present in the HTML, then POST THROUGH the form and
assert the value persists as a ``DynamicFieldValue`` row.

The final test also covers the seed-recipe entity_type mismatch:
``seed_dynamic_field_recipes`` historically wrote bare ``"student"``
entity_types that no form queried (forms key on ``"people.studentprofile"``),
so every seeded recipe was invisible.

Both render assertions FAIL against HEAD before the fix (input absent /
entity_type mismatch) and PASS after.
"""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import unwrap_value
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership


class StudentCreateFormDynamicRenderTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="EAV Render School",
            slug="eav-render-school",
            subdomain="eav-render-school",
            is_active=True,
        )
        # Superuser bypasses the people.add_studentprofile gate; the primary
        # SchoolMembership lets resolve_request_school pin the tenant under the
        # test client (no subdomain middleware runs there).
        self.user = User.objects.create_superuser(
            username="admin@eav-render.test",
            email="admin@eav-render.test",
            password="test-pass-123",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:backend_student_create")

    def _define(self, field_key, *, label=None, data_type="string", school=True):
        return DynamicFieldDefinition.objects.create(
            entity_type="people.studentprofile",
            field_key=field_key,
            label=label or field_key.replace("_", " ").title(),
            data_type=data_type,
            school=self.school if school else None,
            is_active=True,
        )

    def test_school_dynamic_field_input_is_rendered(self):
        self._define("udise_code", label="UDISE+ school code")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
        html = resp.content.decode()
        self.assertIn(
            'name="dyn_udise_code"',
            html,
            msg="dynamic EAV input was not emitted in the student create form "
            "(M5 render leg — the browser can never submit an unrendered field).",
        )

    def test_rendered_dynamic_value_round_trips_to_db(self):
        self._define("udise_code", label="UDISE+ school code")

        # RENDER leg: the input must be present so a browser submits it.
        get_html = self.client.get(self.url).content.decode()
        self.assertIn('name="dyn_udise_code"', get_html)

        # SUBMIT leg: post through the form (only first/last name are required).
        resp = self.client.post(
            self.url,
            {
                "first_name": "Asha",
                "last_name": "Kumar",
                "dyn_udise_code": "UDISE-RENDER-7788",
            },
        )
        self.assertIn(resp.status_code, (302, 303), msg=resp.content[:600])

        student = StudentProfile.objects.get(first_name="Asha", last_name="Kumar")
        value = DynamicFieldValue.objects.filter(
            entity_type="people.studentprofile",
            entity_id=str(student.pk),
            field_key="udise_code",
            school=self.school,
        ).first()
        self.assertIsNotNone(
            value, msg="dynamic value was not persisted after the form POST."
        )
        self.assertEqual(unwrap_value(value.value_json), "UDISE-RENDER-7788")

    def test_seeded_platform_recipe_is_visible_on_form(self):
        # seed_dynamic_field_recipes writes platform-wide (school=None) rows; the
        # form query includes school__isnull=True, so they must appear.
        call_command("seed_dynamic_field_recipes")
        html = self.client.get(self.url).content.decode()
        self.assertIn(
            'name="dyn_preferred_name"',
            html,
            msg="seeded platform recipe was invisible on the student form — "
            "seed_dynamic_field_recipes entity_type must match the form "
            "vocabulary (people.studentprofile), not the bare noun 'student'.",
        )
