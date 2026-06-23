"""Local-first grading-scale binding for the teacher marks-entry grid.

The de-Cameroon grade-scale pass bound the six ``max="20"`` mark inputs to the
school's operational score-scale max (``resolve_school_score_scale`` → 20
francophone, 100 percentage, 4 GPA) via ``_normalized_scale_max`` plus the
``{{ max_score|default:20 }}`` template binding. These no-DB tests cover the two
additions this pass made; the resolver itself is DB-tested in
``test_grading_provisioning.py`` (CM/FR→20, NG→100, US→4), so it is not re-tested
here.

1. ``_normalized_scale_max`` renders each scale as a clean HTML ``max=`` value and
   never breaks on junk input (back-compat /20 default).
2. The template binding falls back to 20 when no ``max_score`` is supplied, so any
   other render path — or a regression that drops the context key — stays /20.
"""

from __future__ import annotations

from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.evals.views import _normalized_scale_max


class NormalizedScaleMaxTests(SimpleTestCase):
    def test_francophone_20_stays_int(self) -> None:
        self.assertEqual(_normalized_scale_max(Decimal("20")), 20)

    def test_percentage_100(self) -> None:
        self.assertEqual(_normalized_scale_max(Decimal("100")), 100)

    def test_gpa_4_whole_is_int_not_float(self) -> None:
        # Decimal("4.0") is whole → int 4, so the attribute renders max="4" not "4.0".
        self.assertEqual(_normalized_scale_max(Decimal("4.0")), 4)

    def test_fractional_scale_keeps_one_decimal(self) -> None:
        self.assertEqual(_normalized_scale_max(Decimal("7.5")), 7.5)

    def test_plain_float_and_int_inputs(self) -> None:
        self.assertEqual(_normalized_scale_max(100.0), 100)
        self.assertEqual(_normalized_scale_max(20), 20)

    def test_junk_falls_back_to_20(self) -> None:
        # None / non-numeric must never break the marks-grid render.
        self.assertEqual(_normalized_scale_max(None), 20)
        self.assertEqual(_normalized_scale_max("not-a-number"), 20)


class MaxScoreTemplateBindingTests(SimpleTestCase):
    BINDING = Template('<input max="{{ max_score|default:20 }}">')

    def test_renders_supplied_scale(self) -> None:
        self.assertIn('max="100"', self.BINDING.render(Context({"max_score": 100})))

    def test_defaults_to_20_when_absent(self) -> None:
        # Back-compat: a render path that doesn't pass max_score still gets /20.
        self.assertIn('max="20"', self.BINDING.render(Context({})))

    def test_zero_or_empty_falls_back_to_20(self) -> None:
        # The default filter fires on falsy input → never an empty or zero max bound.
        self.assertIn('max="20"', self.BINDING.render(Context({"max_score": 0})))
        self.assertIn('max="20"', self.BINDING.render(Context({"max_score": ""})))
