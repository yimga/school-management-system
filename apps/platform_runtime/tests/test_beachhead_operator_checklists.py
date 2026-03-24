"""Operator checklists (wedges 1–45) resolve on manager urlconf."""

from django.test import SimpleTestCase
from django.test.utils import override_settings

from apps.platform_runtime.beachhead_operator_checklists import (
    beachhead_wedge_ids,
    build_resolved_beachhead_checklist,
)
from apps.schools.super_views_wedge import _safe_reverse


class BeachheadOperatorChecklistTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_all_wedges_have_actionable_checklist_rows(self):
        for wid in beachhead_wedge_ids():
            rows = build_resolved_beachhead_checklist(wid, _safe_reverse)
            self.assertGreaterEqual(
                len(rows),
                4,
                msg=f"wedge {wid} checklist too short",
            )
            for row in rows:
                self.assertTrue(
                    row.get("url") or row.get("path_doc"),
                    msg=f"wedge {wid} row {row.get('label')!r} has no url or path_doc",
                )
