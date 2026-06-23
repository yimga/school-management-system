"""Local-first exam-board country filtering (the owner's "US school sees GCE" bug).

Pure no-DB SimpleTestCase coverage of apps.academics.exam_boards.
"""
from django.test import SimpleTestCase

from apps.academics.exam_boards import (
    allowed_board_choices,
    allowed_board_values,
    is_board_available_for_country,
)
from apps.academics.models import CertificationExamSession

Board = CertificationExamSession.Board
_ALL = {value for value, _label in Board.choices}


class ExamBoardCountryFilterTests(SimpleTestCase):
    def test_us_excludes_other_countries_boards(self):
        """The reported bug: a US school must NOT see GCE/WAEC/Baccalauréat."""
        vals = allowed_board_values("US")
        self.assertNotIn(Board.GCE_BOARD.value, vals)
        self.assertNotIn(Board.WAEC.value, vals)
        self.assertNotIn(Board.KCSE.value, vals)
        self.assertNotIn(Board.BAC_FR.value, vals)
        self.assertIn(Board.AP_CB.value, vals)  # College Board AP/SAT
        self.assertIn(Board.IB.value, vals)  # international, always available

    def test_cameroon_includes_gce(self):
        vals = allowed_board_values("CM")
        self.assertIn(Board.GCE_BOARD.value, vals)
        self.assertIn(Board.OBC.value, vals)
        self.assertNotIn(Board.AP_CB.value, vals)
        self.assertIn(Board.IGCSE_CIE.value, vals)  # international, always available

    def test_nigeria_includes_waec_neco(self):
        vals = allowed_board_values("NG")
        self.assertIn(Board.WAEC.value, vals)
        self.assertIn(Board.NECO.value, vals)
        self.assertNotIn(Board.GCE_BOARD.value, vals)

    def test_unknown_country_fails_open_to_full_list(self):
        self.assertEqual(set(allowed_board_values("ZZ")), _ALL)

    def test_empty_or_none_country_fails_open(self):
        self.assertEqual(set(allowed_board_values("")), _ALL)
        self.assertEqual(set(allowed_board_values(None)), _ALL)

    def test_case_insensitive_country(self):
        self.assertEqual(allowed_board_values("us"), allowed_board_values("US"))
        self.assertEqual(allowed_board_values(" Cm "), allowed_board_values("CM"))

    def test_choices_preserve_enum_order_and_labels(self):
        choices = allowed_board_choices("US")
        canonical_order = [value for value, _label in Board.choices]
        got_order = [value for value, _label in choices]
        self.assertEqual(got_order, [v for v in canonical_order if v in dict(choices)])
        # Labels are the canonical enum labels (not re-derived).
        self.assertEqual(
            dict(choices)[Board.AP_CB.value],
            dict(Board.choices)[Board.AP_CB.value],
        )

    def test_choices_subset_of_full_choices(self):
        """Filtering only ever narrows — never invents a value the model rejects."""
        for cc in ("US", "CM", "NG", "FR", "DE", "GB", "KE"):
            allowed = set(allowed_board_values(cc))
            self.assertTrue(allowed.issubset(_ALL), cc)

    def test_is_board_available(self):
        self.assertFalse(is_board_available_for_country(Board.GCE_BOARD.value, "US"))
        self.assertTrue(is_board_available_for_country(Board.GCE_BOARD.value, "CM"))
        self.assertTrue(is_board_available_for_country(Board.IB.value, "US"))
