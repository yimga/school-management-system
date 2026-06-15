"""Gap-closure (2026-06-14) — attendance ticker reads the real model, scoped.

Plain ``unittest`` (no DB).

`_source_tenant_attendance_milestones` imported a non-existent
`apps.attendance.models.AttendanceRecord` (swallowed -> the "N attendance
records logged today" ticker row never appeared). The real model is
`academics.Attendance`, which carries a school FK — so the count MUST be scoped
by request.school (a bare `.filter()` would leak across tenants and trip
scan_tenant_queryset_safety). This wires it to the real model using the same
tenant-scoping idiom as the sibling ticker sources.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class AttendanceTickerSourceScopedTests(unittest.TestCase):

    def test_phantom_import_gone_real_model_used(self) -> None:
        src = (
            REPO / "apps" / "siteconfig" / "cockpit_activity_ticker_realdata.py"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("apps.attendance.models", src)
        self.assertIn("from apps.academics.models import Attendance", src)

    def test_source_is_tenant_scoped(self) -> None:
        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _source_tenant_attendance_milestones,
        )

        body = inspect.getsource(_source_tenant_attendance_milestones)
        # Must scope by school_id and never query unscoped.
        self.assertIn("school_id=school_id", body)
        self.assertNotIn("Attendance.objects.filter(**", body.replace("school_id=school_id,", "X"))

    def test_no_tenant_returns_empty_no_leak(self) -> None:
        from types import SimpleNamespace

        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _source_tenant_attendance_milestones,
        )

        # No tenant context -> empty list, never a cross-tenant aggregate.
        self.assertEqual(
            _source_tenant_attendance_milestones(SimpleNamespace(school=None)), []
        )

    def test_real_model_has_scope_and_ts_fields(self) -> None:
        from apps.academics.models import Attendance

        names = {f.name for f in Attendance._meta.get_fields()}
        self.assertIn("school", names)
        self.assertTrue("created_at" in names or "date" in names)


if __name__ == "__main__":
    unittest.main()
