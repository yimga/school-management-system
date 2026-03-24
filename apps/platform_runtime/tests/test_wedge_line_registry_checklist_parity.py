"""Registry line IDs 1–45 match operator checklist module keys (nothing missing)."""

from django.test import SimpleTestCase

from apps.platform_runtime.beachhead_operator_checklists import beachhead_wedge_ids
from apps.platform_runtime.wedge_line_registry import WEDGE_LINES, assert_wedge_lines_complete


class WedgeLineRegistryChecklistParityTests(SimpleTestCase):
    def test_registry_ids_match_checklist_coverage(self):
        assert_wedge_lines_complete()
        reg_ids = {int(row["id"]) for row in WEDGE_LINES}
        chk_ids = set(beachhead_wedge_ids())
        expected = set(range(1, 46))
        self.assertEqual(reg_ids, expected, "WEDGE_LINES must cover 1..45 exactly")
        self.assertEqual(
            chk_ids,
            expected,
            "beachhead_wedge_ids() must match registry (hand-authored + bootstrap)",
        )
        self.assertEqual(reg_ids, chk_ids)
