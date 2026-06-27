"""Regression: the Applicant CREATE VIEW persists dynamic custom-field VALUES.

Bug (audit metric #5, wave-2 follow-up): wave-1 fixed ``ApplicantCreateForm`` to
RENDER the correct ``people.applicant`` EAV fields, but ``backend_applicant_create``
never called ``save_dynamic_fields_for_model`` after saving the Applicant — unlike
the student path (``backend_student_create``). So an admissions-defined custom
field would appear on the form, the operator would fill it in, and the submitted
value was silently dropped on save.

The fix wires ``save_dynamic_fields_for_model(..., model=Applicant,
instance=<saved applicant>, school=<school>)`` into the view's successful-save
path (inside ``transaction.atomic()``), and passes ``school=school`` to the form
so the EAV fields are actually attached + validated.

These DB-backed tests POST the create form with a value for an Applicant-scoped
custom field and assert a tenant-scoped ``DynamicFieldValue`` row persists for the
new applicant.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import unwrap_value
from apps.people.models import Applicant
from apps.schools.models import School, SchoolMembership


class ApplicantCreateViewDynamicValuePersistenceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Applicant Value School",
            slug="applicant-value-school",
            subdomain="applicant-value-school",
            is_active=True,
        )
        # Superuser bypasses the ``people.add_applicant`` permission gate; the
        # SchoolMembership lets ``resolve_request_school`` pin the tenant when no
        # subdomain middleware runs under the test client.
        self.user = User.objects.create_superuser(
            username="admin@applicant-value.test",
            email="admin@applicant-value.test",
            password="test-pass-123",
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        # Admissions-defined custom field, correctly keyed to the Applicant.
        DynamicFieldDefinition.objects.create(
            entity_type="people.applicant",
            field_key="referral_agency",
            label="Referral Agency",
            data_type="string",
            school=self.school,
            is_active=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:backend_applicant_create")

    def _post_payload(self, **overrides):
        payload = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "lead_source": "Website",
            "stage": Applicant.Stage.LEAD,
            "dyn_referral_agency": "Bright Futures NGO",
        }
        payload.update(overrides)
        return payload

    def test_create_view_persists_dynamic_field_value(self):
        resp = self.client.post(self.url, self._post_payload())
        # Successful create redirects to the list (or save-redirect target).
        self.assertIn(resp.status_code, (302, 303), msg=resp.content[:500])

        applicant = Applicant.objects.get(
            school=self.school, email="ada@example.com"
        )

        value = DynamicFieldValue.objects.filter(
            entity_type="people.applicant",
            entity_id=str(applicant.pk),
            field_key="referral_agency",
            school=self.school,
        ).first()
        self.assertIsNotNone(
            value,
            msg=(
                "Applicant custom-field VALUE was not persisted — the create view "
                "did not call save_dynamic_fields_for_model (metric #5 gap)."
            ),
        )
        self.assertEqual(unwrap_value(value.value_json), "Bright Futures NGO")

    def test_persisted_value_is_tenant_scoped(self):
        """The stored DynamicFieldValue belongs to the creating tenant only."""
        other_school = School.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        self.client.post(self.url, self._post_payload())

        applicant = Applicant.objects.get(
            school=self.school, email="ada@example.com"
        )
        # The value row is scoped to self.school, never the unrelated tenant.
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                entity_id=str(applicant.pk),
                field_key="referral_agency",
                school=self.school,
            ).exists()
        )
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_id=str(applicant.pk),
                field_key="referral_agency",
                school=other_school,
            ).exists()
        )
