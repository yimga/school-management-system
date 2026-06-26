"""Dynamic EAV fields render on backend people forms."""

from django.test import TestCase

from apps.metadata.country_eav_catalog import seed_country_eav_definitions
from apps.metadata.dynamic_forms import save_dynamic_fields_for_model
from apps.metadata.models import DynamicFieldDefinition
from apps.metadata.services import get_dynamic_field_value
from apps.people.forms_backend import StudentCreateForm
from apps.people.models import StudentProfile
from apps.schools.models import School


class DynamicStudentFormTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="EAV Form School",
            slug="eav-form-school",
            country_code="IN",
        )
        seed_country_eav_definitions(school=self.school, country_code="IN")

    def test_student_create_form_includes_country_eav_fields(self):
        form = StudentCreateForm(school=self.school)
        self.assertIn("dyn_aadhaar_reference", form.fields)
        self.assertIn("dyn_udise_code", form.fields)

    def test_save_dynamic_fields_persists_values(self):
        from django import forms

        class _StubForm(forms.Form):
            dyn_aadhaar_reference = forms.CharField(required=False)

        form = _StubForm(data={"dyn_aadhaar_reference": "1234-5678-9012"})
        self.assertTrue(form.is_valid())
        student = StudentProfile.objects.create(
            first_name="Asha",
            last_name="Kumar",
            school=self.school,
        )
        save_dynamic_fields_for_model(
            form,
            instance=student,
            school=self.school,
            model=StudentProfile,
        )
        self.assertEqual(
            get_dynamic_field_value(student, "aadhaar_reference", school=self.school),
            "1234-5678-9012",
        )
        student.refresh_from_db()
        self.assertIn("1234", student.search_index)

    def test_dynamic_value_searchable_in_student_list(self):
        from apps.people.student_search import filter_students_by_search

        student = StudentProfile.objects.create(
            first_name="Ravi",
            last_name="Nair",
            school=self.school,
        )
        from django import forms

        class _StubForm(forms.Form):
            dyn_aadhaar_reference = forms.CharField(required=False)

        form = _StubForm(data={"dyn_aadhaar_reference": "UNIQUE-AADHAAR-XYZ"})
        form.is_valid()
        save_dynamic_fields_for_model(
            form,
            instance=student,
            school=self.school,
            model=StudentProfile,
        )
        qs = StudentProfile.objects.filter(school=self.school)
        found = list(filter_students_by_search(qs, "UNIQUE-AADHAAR"))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].pk, student.pk)

    def test_provision_seed_creates_definitions(self):
        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=self.school,
                field_key="aadhaar_reference",
                entity_type="people.studentprofile",
            ).exists()
        )
