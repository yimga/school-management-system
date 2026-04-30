"""Substantive conversion path classifier (attendance/marks/reports/payments)."""

from django.test import SimpleTestCase

from apps.schools.conversion_substantive_actions import (
    path_indicates_substantive_conversion_post,
)


class ConversionSubstantiveActionsTests(SimpleTestCase):
    def test_attendance_paths_match(self):
        self.assertTrue(
            path_indicates_substantive_conversion_post("/portal/take_student_attendance/")
        )
        self.assertTrue(path_indicates_substantive_conversion_post("/foo/attendance/save/"))

    def test_marks_and_reports_match(self):
        self.assertTrue(path_indicates_substantive_conversion_post("/evals/marks/bulk/"))
        self.assertTrue(path_indicates_substantive_conversion_post("/reports/publish/term/"))

    def test_payment_class_paths_match(self):
        self.assertTrue(path_indicates_substantive_conversion_post("/finance/invoices/1/pay/"))

    def test_generic_backend_settings_no_match(self):
        self.assertFalse(path_indicates_substantive_conversion_post("/backend/settings/theme/"))
        self.assertFalse(path_indicates_substantive_conversion_post("/siteconfig/profile/"))
