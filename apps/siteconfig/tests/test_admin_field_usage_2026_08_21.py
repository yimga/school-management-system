"""Proof for usage-derived field visibility and server-side cross-field rules.

The three properties that make usage inference safe rather than presumptuous are
each asserted here directly: it needs a real sample before it says anything, it
stops the moment a person curates the surface, and it never touches a required
field.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear, Term
from apps.schools.models import School
from apps.siteconfig.admin_field_usage import (
    MIN_ROWS_DEFAULT,
    derive_unused_optional_fields,
    invalidate,
)
from apps.siteconfig.admin_form_intelligence import (
    AdminFieldVisibilityService,
    _containment_error,
    _surface_key,
    build_admin_field_contract,
)
from config.admin import tenant_admin_site


class FieldUsageInferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="field-usage-admin",
            email="field-usage@example.test",
            password="test-only-password",
        )
        cls.school = School.objects.create(
            name="Usage School",
            slug="usage-school",
            subdomain="usage-school",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="Usage 2026/2027",
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=300),
            is_active=True,
        )

    def setUp(self):
        cache.clear()

    def _make_terms(self, count, *, custom_label=""):
        """`unique_term_custom_label_per_year` is conditional on a non-empty label,
        so blanks may repeat but real labels have to be distinct per row."""
        start = self.year.start_date
        for index in range(count):
            Term.objects.create(
                school=self.school,
                academic_year=self.year,
                name=f"T{index}",
                custom_label=f"{custom_label} {index}" if custom_label else "",
                start_date=start + timedelta(days=index),
                end_date=start + timedelta(days=index + 1),
            )

    def test_no_inference_below_the_sample_floor(self):
        """Three records is a new school, not evidence that a field is unused."""
        self._make_terms(3)
        unused, rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label", "position"]
        )
        self.assertEqual(rows, 3)
        self.assertEqual(unused, frozenset())

    def test_a_field_never_used_across_a_real_sample_is_inferred_unused(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2, custom_label="")
        unused, rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label", "position"]
        )
        self.assertGreaterEqual(rows, MIN_ROWS_DEFAULT)
        self.assertIn("custom_label", unused)

    def test_a_field_the_school_does_use_is_never_inferred_unused(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2, custom_label="Semester")
        unused, _rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label"]
        )
        self.assertNotIn("custom_label", unused)

    def test_one_used_row_among_many_is_enough_to_keep_a_field(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2, custom_label="")
        term = Term.objects.filter(school=self.school).first()
        term.custom_label = "Semester 1"
        term.save(update_fields=["custom_label"])
        invalidate(Term, self.school)
        unused, _rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label"]
        )
        self.assertNotIn("custom_label", unused)

    def test_inference_is_scoped_to_one_school(self):
        other = School.objects.create(
            name="Other Usage", slug="usage-other", subdomain="usage-other", is_active=True
        )
        other_year = AcademicYear.objects.create(
            school=other,
            name="Other 2026/2027",
            start_date=self.year.start_date,
            end_date=self.year.end_date,
        )
        for index in range(MIN_ROWS_DEFAULT + 2):
            Term.objects.create(
                school=other,
                academic_year=other_year,
                name=f"O{index}",
                custom_label=f"Used Here {index}",
                start_date=self.year.start_date + timedelta(days=index),
                end_date=self.year.start_date + timedelta(days=index + 1),
            )
        # `self.school` has NO rows at all, so nothing may be inferred from the
        # neighbour's dense, fully-populated records.
        unused, rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label"]
        )
        self.assertEqual(rows, 0)
        self.assertEqual(unused, frozenset())

    @override_settings(RMC_ADMIN_FIELD_USAGE_INFERENCE_ENABLED=False)
    def test_inference_can_be_switched_off(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2)
        unused, rows = derive_unused_optional_fields(
            Term, self.school, ["custom_label"]
        )
        self.assertEqual((unused, rows), (frozenset(), 0))

    # -- integration with the rendered contract ---------------------------- #

    def _request(self):
        request = RequestFactory().get("/admin/", HTTP_HOST="usage-school.runmycampus.com")
        request.user = self.user
        request.school = self.school
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        SessionMiddleware(lambda _r: None).process_request(request)
        MessageMiddleware(lambda _r: None).process_request(request)
        return request

    def test_contract_reports_inferred_fields_separately_from_chosen_ones(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2, custom_label="")
        model_admin = tenant_admin_site._registry.get(Term)
        contract = build_admin_field_contract(
            model_admin, self._request(), obj=None, mode="add"
        )
        self.assertIn("custom_label", contract.inferred_hidden_fields)
        self.assertIn("custom_label", contract.hidden_fields)
        self.assertGreaterEqual(contract.inference_sample_rows, MIN_ROWS_DEFAULT)
        payload = contract.as_dict()
        self.assertIn("custom_label", payload["inferredHidden"])
        self.assertTrue(payload["inferenceReason"])

    def test_a_required_field_is_never_inferred_hidden(self):
        self._make_terms(MIN_ROWS_DEFAULT + 2)
        model_admin = tenant_admin_site._registry.get(Term)
        contract = build_admin_field_contract(
            model_admin, self._request(), obj=None, mode="add"
        )
        self.assertEqual(
            set(contract.required_fields) & set(contract.hidden_fields), set()
        )

    def test_the_persons_own_choice_switches_inference_off_entirely(self):
        """Once someone curates this surface, their answer is the whole answer."""
        self._make_terms(MIN_ROWS_DEFAULT + 2, custom_label="")
        request = self._request()
        model_admin = tenant_admin_site._registry.get(Term)
        surface = _surface_key(
            host="usage-school.runmycampus.com",
            admin_site_name=model_admin.admin_site.name,
            model_label=Term._meta.label_lower,
            mode="add",
        )
        AdminFieldVisibilityService.write(
            user=self.user,
            surface_key=surface,
            hidden_fields=["position"],
            allowed_optional_fields=["position", "custom_label"],
        )
        contract = build_admin_field_contract(
            model_admin, request, obj=None, mode="add"
        )
        self.assertEqual(contract.inferred_hidden_fields, ())
        self.assertIn("position", contract.hidden_fields)
        self.assertNotIn(
            "custom_label",
            contract.hidden_fields,
            "inference must not re-hide a field the person left visible",
        )


class CrossFieldContainmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Containment School",
            slug="containment-school",
            subdomain="containment-school",
            is_active=True,
        )
        today = timezone.now().date()
        cls.year_a = AcademicYear.objects.create(
            school=cls.school, name="A", start_date=today, end_date=today + timedelta(days=300)
        )
        cls.year_b = AcademicYear.objects.create(
            school=cls.school,
            name="B",
            start_date=today + timedelta(days=301),
            end_date=today + timedelta(days=600),
        )
        cls.term_of_a = Term.objects.create(
            school=cls.school,
            academic_year=cls.year_a,
            name="FIRST",
            start_date=today,
            end_date=today + timedelta(days=90),
        )

    def test_a_term_from_another_year_is_rejected(self):
        error = _containment_error(
            {"term": self.term_of_a, "academic_year": self.year_b}
        )
        self.assertIsNotNone(error)
        field, message = error
        self.assertEqual(field, "term")
        self.assertIn("different", message.lower())

    def test_a_matching_pair_is_accepted(self):
        self.assertIsNone(
            _containment_error({"term": self.term_of_a, "academic_year": self.year_a})
        )

    def test_a_partial_selection_is_not_an_error(self):
        self.assertIsNone(_containment_error({"term": self.term_of_a}))
        self.assertIsNone(_containment_error({"academic_year": self.year_a}))
        self.assertIsNone(_containment_error({}))

    def test_unrelated_values_are_ignored(self):
        self.assertIsNone(
            _containment_error({"term": "not-a-model", "academic_year": self.year_a})
        )
