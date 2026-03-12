from unittest.mock import patch

from django.test import TestCase

from apps.reports.services import (
    student_has_financial_clearance,
    student_has_outstanding_returns,
)


class ReportRuntimeSettingsAccessorTests(TestCase):
    def test_financial_clearance_uses_owner_scoped_backend_flags(self):
        site = type(
            "Site",
            (),
            {
                "get_backend_feature_flags": lambda self: {
                    "block_report_download_if_outstanding_balance": False
                }
            },
        )()
        student = type("Student", (), {"school": object()})()

        with patch("apps.reports.services._site_settings_for_school", return_value=site):
            self.assertTrue(student_has_financial_clearance(student, academic_year=object()))

    def test_outstanding_returns_uses_owner_scoped_backend_flags(self):
        site = type(
            "Site",
            (),
            {
                "get_backend_feature_flags": lambda self: {
                    "block_report_download_if_outstanding_returns": False
                }
            },
        )()
        student = type("Student", (), {"school": object()})()

        with patch("apps.reports.services._site_settings_for_school", return_value=site):
            self.assertFalse(student_has_outstanding_returns(student, academic_year=object()))
