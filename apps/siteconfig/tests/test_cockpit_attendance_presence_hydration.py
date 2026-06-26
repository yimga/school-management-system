"""No-DB tests for the attendance-heatmap + presence cockpit elevations."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.siteconfig.cockpit_tenant_v3_realdata import (
    _build_heatmap_cells,
    _is_tenant_admin,
)


class BuildHeatmapCellsTests(SimpleTestCase):
    MONTH_START = date(2026, 6, 1)
    NEXT_MONTH = date(2026, 7, 1)
    TODAY = date(2026, 6, 15)

    def _cells(self, rows):
        return _build_heatmap_cells(rows, self.TODAY, self.MONTH_START, self.NEXT_MONTH)

    def test_covers_every_day_of_month(self):
        cells = self._cells([])
        self.assertEqual(len(cells), 30)  # June has 30 days
        self.assertEqual([c["day"] for c in cells], list(range(1, 31)))

    def test_dominant_status_wins(self):
        rows = [
            {"date": date(2026, 6, 15), "status": "present", "n": 30},
            {"date": date(2026, 6, 15), "status": "absent", "n": 5},
            {"date": date(2026, 6, 16), "status": "late", "n": 2},
        ]
        by_day = {c["day"]: c for c in self._cells(rows)}
        self.assertEqual(by_day[15]["tone"], "present")
        self.assertTrue(by_day[15]["is_today"])
        self.assertEqual(by_day[16]["tone"], "late")

    def test_no_data_weekday_blank_weekend_toned(self):
        by_day = {c["day"]: c for c in self._cells([])}
        for day, cell in by_day.items():
            d = date(2026, 6, day)
            if d.weekday() >= 5:
                self.assertEqual(cell["tone"], "weekend", day)
            else:
                self.assertEqual(cell["tone"], "", day)

    def test_rows_with_missing_date_ignored(self):
        cells = self._cells([{"date": None, "status": "present", "n": 9}])
        self.assertEqual(len(cells), 30)


class IsTenantAdminTests(SimpleTestCase):
    def test_superuser_is_admin(self):
        self.assertTrue(_is_tenant_admin(SimpleNamespace(is_superuser=True)))

    def test_staff_is_admin(self):
        self.assertTrue(_is_tenant_admin(SimpleNamespace(is_staff=True)))

    def test_teacher_is_not_admin(self):
        self.assertFalse(
            _is_tenant_admin(
                SimpleNamespace(role="TEACHER", is_staff=False, is_superuser=False)
            )
        )

    def test_admin_role_is_admin(self):
        from apps.accounts.models import User

        self.assertTrue(
            _is_tenant_admin(
                SimpleNamespace(role=str(User.Role.ADMIN), is_staff=False, is_superuser=False)
            )
        )
