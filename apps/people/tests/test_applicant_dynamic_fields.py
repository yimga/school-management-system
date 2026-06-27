"""Regression: ApplicantCreateForm attaches APPLICANT EAV fields, not TEACHER.

Bug (audit metric #5): ``ApplicantCreateForm.__init__`` called
``attach_dynamic_fields_for_model(..., model=TeacherProfile, ...)``. Because the
helper derives the EAV ``entity_type`` from the model
(``f"{app_label}.{model_name}"``), the Applicant form rendered and would save
custom fields keyed on ``people.teacherprofile`` — i.e. TEACHER custom fields —
while admissions-defined custom fields keyed on ``people.applicant`` never
appeared. The fix passes ``model=Applicant`` so the correct entity_type is used.

These DB-backed tests prove the form now surfaces Applicant-scoped definitions
and no longer leaks Teacher-scoped ones.
"""

from __future__ import annotations

from django.test import TestCase

from apps.metadata.models import DynamicFieldDefinition
from apps.people.forms_backend import ApplicantCreateForm
from apps.schools.models import School


class ApplicantFormDynamicFieldTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Applicant EAV School",
            slug="applicant-eav-school",
        )
        # An admissions-defined custom field, correctly keyed to the Applicant.
        DynamicFieldDefinition.objects.create(
            entity_type="people.applicant",
            field_key="referral_agency",
            label="Referral Agency",
            data_type="string",
            school=self.school,
            is_active=True,
        )
        # A teacher HR custom field that MUST NOT bleed onto the Applicant form.
        DynamicFieldDefinition.objects.create(
            entity_type="people.teacherprofile",
            field_key="payroll_grade_band",
            label="Payroll Grade Band",
            data_type="string",
            school=self.school,
            is_active=True,
        )

    def test_applicant_form_includes_applicant_scoped_field(self):
        form = ApplicantCreateForm(school=self.school)
        self.assertIn(
            "dyn_referral_agency",
            form.fields,
            msg="Applicant-scoped EAV field should render on the Applicant form.",
        )

    def test_applicant_form_excludes_teacher_scoped_field(self):
        form = ApplicantCreateForm(school=self.school)
        self.assertNotIn(
            "dyn_payroll_grade_band",
            form.fields,
            msg=(
                "TEACHER custom field leaked onto the Applicant form — this is "
                "the metric #5 bug (model=TeacherProfile instead of Applicant)."
            ),
        )

    def test_entity_type_resolves_to_applicant(self):
        """Belt-and-suspenders: the helper maps the model to the right key."""
        from apps.metadata.dynamic_forms import _entity_type_for_model
        from apps.people.models import Applicant

        self.assertEqual(_entity_type_for_model(Applicant), "people.applicant")
