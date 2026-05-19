"""AcademicYear dual-calendar display (G-07)."""

from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from apps.academics.models import AcademicYear


class AcademicYearDualCalendarTests(TestCase):
    @patch("apps.platform_runtime.calendar_display.format_dual_calendar_date")
    def test_format_start_date_display_dual(self, mock_dual):
        mock_dual.return_value = "2026-05-18"
        year = Mock()
        year.start_date = date(2026, 5, 18)
        year.school = None
        label = AcademicYear.format_start_date_display(year)
        self.assertEqual(label, "2026-05-18")
        mock_dual.assert_called_once_with(date(2026, 5, 18), school=None)
