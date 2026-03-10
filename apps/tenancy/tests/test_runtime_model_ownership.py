from django.apps import apps as django_apps
from django.test import SimpleTestCase

from apps.academics.models import (
    HolidayCalendar as AcademicHolidayCalendar,
    ReportCardStyleAssignment as AcademicReportCardStyleAssignment,
    RolloverProposal as AcademicRolloverProposal,
)
from apps.accounts.models import RolloverProposal
from apps.schoolops.models import Campus as SchoolOpsCampus
from apps.schools.models import Campus
from apps.siteconfig.models import HolidayCalendar, ReportCardStyleAssignment


class RuntimeModelOwnershipTests(SimpleTestCase):
    def test_shared_modules_alias_extracted_models_from_tenant_apps(self):
        self.assertIs(Campus, SchoolOpsCampus)
        self.assertEqual(Campus._meta.app_label, "schoolops")
        self.assertIs(RolloverProposal, AcademicRolloverProposal)
        self.assertEqual(RolloverProposal._meta.app_label, "academics")
        self.assertIs(ReportCardStyleAssignment, AcademicReportCardStyleAssignment)
        self.assertEqual(ReportCardStyleAssignment._meta.app_label, "academics")
        self.assertIs(HolidayCalendar, AcademicHolidayCalendar)
        self.assertEqual(HolidayCalendar._meta.app_label, "academics")

    def test_shared_app_registry_no_longer_owns_extracted_runtime_models(self):
        for app_label, model_name in (
            ("accounts", "RolloverProposal"),
            ("schools", "Campus"),
            ("siteconfig", "ReportCardStyleAssignment"),
            ("siteconfig", "HolidayCalendar"),
        ):
            with self.subTest(app_label=app_label, model_name=model_name):
                with self.assertRaises(LookupError):
                    django_apps.get_model(app_label, model_name)
