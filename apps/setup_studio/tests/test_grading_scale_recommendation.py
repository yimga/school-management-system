"""10X-B — studio grading wizard recommends the country's scale instead of a blind pick.

list_grading_scales now (a) includes numeric_0_20 (0–20 Francophone systems were
unrepresentable) and (b) flags + front-sorts the school's country-recommended scale.
"""

from django.test import SimpleTestCase, TestCase


class GradingScaleOptionsTests(SimpleTestCase):
    def test_includes_numeric_0_20_and_no_school_has_no_recommendation(self):
        from apps.setup_studio.wizard_resolvers import list_grading_scales

        opts = list_grading_scales(request=None, school=None)
        values = [o["value"] for o in opts]
        self.assertIn("numeric_0_20", values)
        self.assertIn("percentage", values)
        # No school → nothing flagged recommended.
        self.assertFalse(any(o["metadata"].get("recommended") for o in opts))

    def test_scale_type_to_wizard_value_map_is_complete(self):
        from apps.setup_studio.wizard_resolvers import _SCALE_TYPE_TO_WIZARD_VALUE

        valid_wizard_values = {
            "numeric_0_20", "percentage", "gpa_4", "gpa_5",
            "letter", "competency", "points_100", "points_1000",
        }
        for scale_type in ("numeric_0_20", "percentage", "gpa_4_0", "letter_a_e"):
            self.assertIn(scale_type, _SCALE_TYPE_TO_WIZARD_VALUE)
            self.assertIn(_SCALE_TYPE_TO_WIZARD_VALUE[scale_type], valid_wizard_values)


class GradingScaleRecommendationDBTests(TestCase):
    def _school(self, **kw):
        import uuid

        from apps.schools.models import School

        tag = uuid.uuid4().hex[:10]
        return School.objects.create(
            name="GR " + tag, slug=f"gr-{tag}", subdomain=f"gr-{tag}", **kw
        )

    def test_country_recommended_scale_is_flagged_and_first(self):
        from apps.setup_studio.wizard_resolvers import (
            _recommended_grading_scale_value,
            list_grading_scales,
        )

        school = self._school(country_code="US")  # american → gpa_4_0 → "gpa_4"
        rec = _recommended_grading_scale_value(school)
        self.assertTrue(rec)  # a recommendation resolved
        opts = list_grading_scales(request=None, school=school)
        self.assertEqual(opts[0]["value"], rec)  # recommended sorts first
        self.assertTrue(opts[0]["metadata"].get("recommended"))
