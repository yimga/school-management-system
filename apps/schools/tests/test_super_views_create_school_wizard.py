"""BR-12: create_school_wizard re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsCreateSchoolWizardReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_wizard_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_create_school_wizard as wiz

        self.assertIs(super_views.create_school_wizard, wiz.create_school_wizard)
