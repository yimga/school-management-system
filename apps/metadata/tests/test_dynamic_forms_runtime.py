"""Dynamic EAV fields render on backend people forms.

General machinery (persist + search) is exercised on the NON-masked
``udise_code`` field. The masked ``aadhaar_reference`` field (catalog carries
``validation: {"pattern": ..., "store_masked": True}``) has its own dedicated
tests below — a valid value is stored masked (raw never persisted / searchable)
and a malformed value is rejected at form clean.
"""

from django import forms
from django.test import TestCase

from apps.metadata.country_eav_catalog import seed_country_eav_definitions
from apps.metadata.dynamic_forms import (
    attach_dynamic_fields,
    save_dynamic_fields_for_model,
)
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
        # udise_code is NOT store_masked → the raw value round-trips verbatim.
        class _StubForm(forms.Form):
            dyn_udise_code = forms.CharField(required=False)

        form = _StubForm(data={"dyn_udise_code": "UDISE1234567"})
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
            get_dynamic_field_value(student, "udise_code", school=self.school),
            "UDISE1234567",
        )
        student.refresh_from_db()
        self.assertIn("udise1234567", student.search_index)

    def test_dynamic_value_searchable_in_student_list(self):
        from apps.people.student_search import filter_students_by_search

        student = StudentProfile.objects.create(
            first_name="Ravi",
            last_name="Nair",
            school=self.school,
        )

        class _StubForm(forms.Form):
            dyn_udise_code = forms.CharField(required=False)

        form = _StubForm(data={"dyn_udise_code": "UNIQUEUDISEXYZ"})
        form.is_valid()
        save_dynamic_fields_for_model(
            form,
            instance=student,
            school=self.school,
            model=StudentProfile,
        )
        qs = StudentProfile.objects.filter(school=self.school)
        found = list(filter_students_by_search(qs, "UNIQUEUDISE"))
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

    def test_seed_carries_validation_json(self):
        defn = DynamicFieldDefinition.objects.get(
            school=self.school,
            field_key="aadhaar_reference",
            entity_type="people.studentprofile",
        )
        self.assertEqual(defn.validation_json.get("store_masked"), True)
        self.assertTrue(defn.validation_json.get("pattern"))


class DynamicMaskedFieldTests(TestCase):
    """LEG 2 — Aadhaar-style store_masked fields: validated + masked."""

    def setUp(self):
        self.school = School.objects.create(
            name="Masked EAV School",
            slug="masked-eav-school",
            country_code="IN",
        )
        seed_country_eav_definitions(school=self.school, country_code="IN")

    def _bound_form(self, aadhaar_value):
        class _Form(forms.Form):
            pass

        form = _Form(data={"dyn_aadhaar_reference": aadhaar_value})
        attach_dynamic_fields(
            form,
            school=self.school,
            entity_type="people.studentprofile",
        )
        return form

    def test_malformed_masked_value_rejected_by_form(self):
        form = self._bound_form("not-a-valid-aadhaar")
        self.assertFalse(form.is_valid())
        self.assertIn("dyn_aadhaar_reference", form.errors)

    def test_valid_value_stored_masked_raw_absent(self):
        form = self._bound_form("1234-5678-9012")
        self.assertTrue(form.is_valid(), msg=form.errors.as_json())
        student = StudentProfile.objects.create(
            first_name="Meera",
            last_name="Iyer",
            school=self.school,
        )
        save_dynamic_fields_for_model(
            form,
            instance=student,
            school=self.school,
            model=StudentProfile,
        )
        stored = get_dynamic_field_value(
            student, "aadhaar_reference", school=self.school
        )
        # Raw PII is NOT stored; only the masked form (last 4 revealed).
        self.assertEqual(stored, "••••-••••-9012")
        self.assertNotEqual(stored, "1234-5678-9012")

        # The raw value must not leak into the student search index.
        student.refresh_from_db()
        self.assertNotIn("1234-5678-9012", student.search_index)
        self.assertNotIn("5678", student.search_index)
        # The revealed suffix is still searchable (masked form is indexed).
        self.assertIn("9012", student.search_index)

    def test_detail_rows_surface_masked_value_only(self):
        from apps.metadata.dynamic_forms import dynamic_field_display_rows

        form = self._bound_form("1234-5678-9012")
        self.assertTrue(form.is_valid(), msg=form.errors.as_json())
        student = StudentProfile.objects.create(
            first_name="Nisha",
            last_name="Rao",
            school=self.school,
        )
        save_dynamic_fields_for_model(
            form,
            instance=student,
            school=self.school,
            model=StudentProfile,
        )
        rows = dynamic_field_display_rows(
            student, school=self.school, entity_type="people.studentprofile"
        )
        aadhaar_rows = [r for r in rows if "Aadhaar" in r["label"]]
        self.assertEqual(len(aadhaar_rows), 1)
        self.assertEqual(aadhaar_rows[0]["value"], "••••-••••-9012")
        self.assertNotIn("1234-5678-9012", aadhaar_rows[0]["value"])
