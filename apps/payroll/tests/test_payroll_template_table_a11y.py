"""N3: payroll portal templates use scope=\"col\" on data table headers."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class PayrollTableHeaderScopeTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_employee_payslips_table_headers(self):
        text = self._read("templates", "payroll", "employee_payslips.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)

    def test_dashboard_runs_table_headers(self):
        text = self._read("templates", "payroll", "dashboard.html")
        self.assertIn('scope="col">Period', text)
        self.assertIn('class="visually-hidden">Actions', text)

    def test_employee_leave_history_table_headers(self):
        text = self._read("templates", "payroll", "employee_leave.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)

    def test_run_detail_payslips_table_headers(self):
        text = self._read("templates", "payroll", "run_detail.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)
