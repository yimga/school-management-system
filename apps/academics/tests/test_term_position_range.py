"""Wave 6 — Term.position is no longer capped at 4 (Cameroon 3-term assumption).

A DB CheckConstraint + clean() limited terms to 1–4, blocking 2-semester+summer, quarter,
and 5+-period/modular calendars. The cap is now 1–12 (aligned with
RegionConfig.term_count_per_year); terms beyond the named choices use custom_label.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]


class TermPositionRangeTests(SimpleTestCase):
    def _clean_ok(self, pos):
        from apps.academics.models import Term

        try:
            Term(position=pos).clean()
            return True
        except ValidationError:
            return False

    def test_accepts_1_to_12_and_null(self):
        for pos in (None, 1, 4, 5, 8, 12):
            self.assertTrue(self._clean_ok(pos), pos)

    def test_rejects_out_of_range(self):
        self.assertFalse(self._clean_ok(0))
        self.assertFalse(self._clean_ok(13))

    def test_constraint_widened_in_model(self):
        from apps.academics.models import Term

        names = {c.name for c in Term._meta.constraints}
        self.assertIn("term_position_range_1_12_or_null", names)
        self.assertNotIn("term_position_range_1_4_or_null", names)

    def test_migration_exists(self):
        self.assertTrue(
            (
                _ROOT
                / "apps/academics/migrations/0058_remove_term_term_position_range_1_4_or_null_and_more.py"
            ).exists()
        )
