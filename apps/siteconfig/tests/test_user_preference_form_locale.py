"""UserPreferenceForm locale/region choice wiring."""

from django.test import TestCase

from apps.siteconfig.forms import (
    UserPreferenceForm,
    _build_preferred_language_choices,
    _build_preferred_region_choices,
)


class UserPreferenceFormLocaleTests(TestCase):
    def test_language_choices_include_default_and_english(self):
        choices = _build_preferred_language_choices()
        self.assertGreaterEqual(len(choices), 2)
        self.assertEqual(choices[0][0], "")
        codes = [c for c, _ in choices]
        self.assertIn("en", codes)

    def test_region_choices_include_default_row(self):
        choices = _build_preferred_region_choices()
        self.assertGreaterEqual(len(choices), 1)
        self.assertEqual(choices[0][0], "")

    def test_form_widgets_are_selects_with_prefs_class(self):
        form = UserPreferenceForm()
        self.assertEqual(
            form.fields["preferred_language"].widget.__class__.__name__,
            "Select",
        )
        self.assertIn(
            "rmc-prefs-select",
            form.fields["preferred_language"].widget.attrs.get("class", ""),
        )
        self.assertEqual(
            form.fields["preferred_region"].widget.__class__.__name__,
            "Select",
        )
